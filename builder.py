#!/usr/bin/env python3
import argparse #Pour créer la commande d'interface et ses arguments
#import glob #
import os #Pour créer les caches, les figures, les fichiers
import random #Randomisation, nécessaire pour python
import subprocess #Pour invoquer Sagemath à partir de python
import tempfile #Utilisé dans la création de fichiers Sage temporaires
import yaml #Pour lire les fichiers de question et le fichier de configuration
import json #Utilisé pour le debuggage 
import copy #Permet la copie de différents objets sans modifier l'original
from jinja2 import Environment, FileSystemLoader, Template #Utiliser pour créer les fichiers Tex à partir d'un canevas

# --------------------------------------------------------------------
def load_questions(test_config, seed=None):
    """
    Charge les questions et variantes spécifiées dans tes_config.
    
    test_config : un dictionnaire qui décrit quelles questions et variantes peuvent être incluses.
    seed: Un entier. Permet de randomiser la sélection, mais de reproduire ce choix si nécessaire.
    
    Load only the questions/variants specified in test_config.

    test_config: dict specifying which questions and variants to include.
    seed: int or None. If provided, ensures deterministic random selection
          when choose < len(pool).
    """
    rng = random.Random(seed) if seed is not None else random # Crée un nombre aléatoire qui servira à choisir un sous-ensemble de questions si l'option est utilisée.
    all_questions = []    #Liste des questions à charger
    for qid, rules in test_config.items():  #Boucle sur les questions spécifiées par qid et leurs options (variantes à choisir, combien, groupement ou non, etc.)
        qfile = f"questions/{qid}.yaml"  #Le nom du fichier doit être qid.yaml
        if not os.path.exists(qfile):
            raise SystemExit(f"Missing question file: {qfile}")

        try:
            with open(qfile, "r") as f:
                qdata = yaml.safe_load(f)  #On charge la question
        except yaml.YAMLError as e:
            raise SystemExit(
                f"\nYAML parse error in {qfile}:\n{e}\n"
                "Hint: In double-quoted YAML strings, escape LaTeX backslashes like \\\\sin, \\\\pi, \\\\frac, etc."
            )

        # Get all variants
        if "variants" not in qdata or not qdata["variants"]: #On regarde si l'option variantes est présente
            raise SystemExit(
                f"Question file {qfile} must define a non-empty 'variants' list."
            )

        pool = []
        for var in qdata["variants"]:
            if "sub_id" not in var:
                raise SystemExit(f"Variant in {qfile} is missing required 'sub_id'.")
            q_variant = {**qdata, **var}  #Fusion des dictionnaires qdata et var
            q_variant["id"] = qdata["id"]
            q_variant.pop("variants", None)
            pool.append(q_variant)  #On ajoute la variante aux possibilités

        # --- DEBUG: show pool of sub_ids ---
        #print(f"[DEBUG] Question {qid} pool of sub_ids: {[v['sub_id'] for v in pool]}")

        # Apply selection rules
        select_spec = rules.get("select", "all") #On va chercher les variantes à choisir;
        choose_spec = rules.get("choose", None)  #Et combien de celles-ci

        # ------------------------------------------------------------
        # Groupement en sous-questions
        # ------------------------------------------------------------
		# These are optional in config and default to 'none' (no grouping)
        # and an empty group_text (no intro line).
        grouping = rules.get("grouping", "none")
        group_text = rules.get("group_text", "")
        n_ans = rules.get("n_ans", None)

        # --- DEBUG: show select/choose spec ---
        #print(f"[DEBUG] Question {qid} select_spec: {select_spec}, choose_spec: {choose_spec}")

        if select_spec == "all":
            selected = pool
        else:
            selected = [v for v in pool if v["sub_id"] in select_spec]

        # --- DEBUG: show selected after filtering ---
        #print(f"[DEBUG] Question {qid} selected after filtering: {[v['sub_id'] for v in selected]}")

        # Sélection des variantes parmi les possibilités
        if choose_spec is not None:
            if choose_spec == "all" or choose_spec >= len(selected):
                chosen = selected
            else:
                chosen = rng.sample(selected, choose_spec)
        else:
            chosen = selected

        # --- DEBUG: show chosen variants ---
        #print(f"[DEBUG] Question {qid} chosen variants: {[v['sub_id'] for v in chosen]}")

        # ------------------------------------------------------------
        # Attach config-level attributes (grouping + group_text + n_ans)
        # ------------------------------------------------------------
        for q in chosen:
            q["grouping"] = grouping
            q["group_text"] = group_text
            q["n_ans"] = n_ans

        all_questions.extend(chosen)

    return all_questions
# --------------------------------------------------------------------
def run_sage_code(code, debug=False, seed=None):
    """
    Exécute un code Sage pour définir des variables de la question. Retourne un dictionnaire pyhton.
    
    Run a small Sage snippet that defines variables for LaTeX templating.
    Returns a dict of basic Python types only (int, float, str, bool).
    """
    #On s'assure de mettre le seed dans Sage pour reproduire les résultats 
    sage_script = f"""
set_random_seed({seed}) 
{code}

# Collect only basic variables for JSON									   
data = {{}}
for var in list(locals().keys()):
    if var.startswith("__"):
        continue
    val = locals()[var]
    if isinstance(val, (int, float, str, bool)):
        data[var] = val

import json
print(json.dumps(data))
"""
    with tempfile.NamedTemporaryFile("w", suffix=".sage", delete=False) as tmp:
        tmp.write(sage_script)
        tmp_name = tmp.name

    try:
        result = subprocess.run(
            ["sage", tmp_name],
            check=True,
            capture_output=True,
            text=True,
        )
        if debug:
            print(f"[Sage stdout]\n{result.stdout}")
            print(f"[Sage stderr]\n{result.stderr}")
        local_vars = json.loads(result.stdout)
        return local_vars
    except subprocess.CalledProcessError as e:
        raise SystemExit(
            f"\n[Error running Sage]\n"
            f"Sage stderr:\n{e.stderr}\n"
        )
    finally:
        os.remove(tmp_name)


# --------------------------------------------------------------------
# Extract all data from a question. Returns a question with added info and stuff needed.

def render_question(q, version, seed=None, debug=False, usecache=False):
    """
    Génère les éléments nécessaires pour construire une question. Les paramètres et les figures.
    
    Formats supportés:
      - open (question ouverte)
      - tf (Vrai ou faux)
      - mcq (choix de réponses)
    
    Render one question: handle per-question seeded generate_params and generate_figure.

    Supported types:
      - open
      - tf
      - mcq
    """
    q_copy = q.copy()

    # ------------------------------------------------------------
    # On définit le type de la question
    # ------------------------------------------------------------
    q_copy["type"] = q.get("type", "open")

    # Le chemin menant au dossier cache pour aller chercher les seeds précédemment utilisés. 
    cache_folder = "cache"
    os.makedirs(cache_folder, exist_ok=True)
    cache_file = os.path.join(cache_folder, "seeds_cache.yaml")

    # Chargement du fichier cache, s'il existe.
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            cache = yaml.safe_load(f) or {}
    else:
        cache = {}

    # Création d'un seed déterministe par question et par version.
    if seed is not None:
        question_seed = seed + (hash(q["id"]) % 10000)+(hash(q["sub_id"]) % 10000) + version
        #print(question_seed)
    else:
        question_seed = None

    # On réutilise les données en cache au besoin. En particulier, si l'option 'usecache' est passée. Évite de regénérer les paramètres aléatoires.
    cache_key = f"{q['id']}_variante{q['sub_id']}_version{version}"
    if usecache and cache_key in cache:
        # On va chercher les paramètres
        q_copy.update(cache[cache_key])
    else:
        # On génère les paramètres au besoin
        if "generate_params" in q and q["generate_params"]:
            local_vars = run_sage_code(
                q["generate_params"], debug=debug, seed=question_seed
            )
            q_copy.update(local_vars)
            # On ajoute les paramètres à la cache
            cache[cache_key] = local_vars
            with open(cache_file, "w") as f:
                yaml.safe_dump(cache, f)

    # ------------------------------------------------------------
    # Choix de réponses : sélection des réponses et randomisation de l'ordre
    # ------------------------------------------------------------
    if q_copy["type"] == "mcq":
        # On met les bonnes réponses dans une liste
        correct = q.get("answer", [])
        #print('correct initial=',correct)
        if not isinstance(correct, list):
            correct = [correct]
        #print('correct 2=',correct)
        wrong = q.get("wrong_ans", [])
        #print('Wrong',wrong)
        n_ans = q.get("n_ans", None)
        #On ajoute au moins une bonne réponse
        rng = random.Random(question_seed) if question_seed is not None else random
        answer1=rng.sample(correct,1)
        #correct.remove(answer1)
        # On sélectionne les mauvaises réponses parmi les possibilités
        ## TEST pour plus d'une bonne réponse
        #if n_ans is not None and n_ans < len(wrong):
        #    rng = random.Random(question_seed) if question_seed is not None else random
        #    wrong = rng.sample(wrong, n_ans)

        # On combine les options et on mélange l'ordre.
        options = []
        for ans in correct:
            options.append({"text": ans, "is_correct": True}) if ans!=answer1[0] else None
        for ans in wrong:
            options.append({"text": ans, "is_correct": False})
        if n_ans is not None and n_ans<= len(options):
            options=rng.sample(options,n_ans-1)
        options.append({"text":answer1[0],"is_correct":True})
        #rng = random.Random(question_seed) if question_seed is not None else random
        #print(options)
        rng.shuffle(options)

        q_copy["options"] = options

    # ------------------------------------------------------------
    # Création des figures à l'aide de Sagemath
    # ------------------------------------------------------------
    if "generate_figure" in q and q["generate_figure"]:
        filename = f"figures/{q['id']}_variante{q['sub_id']}_version{version}.png" #Nom du fichier dépendant de la question, de la variante et de la version
        os.makedirs("figures", exist_ok=True)

        # Ajout du nom du fichier aux informations de la question.
        q_copy["filename"] = filename

        # On vérifie si la cache peut être utilisée.
        if not (usecache and os.path.exists(filename)):
            # Transformation avec Jinja pour que les instances {{var}} soient correctement substituées.
            sage_template = Template(q["generate_figure"])
            sage_code = sage_template.render(**q_copy)

            # Ajout du seed
            if question_seed is not None:
                sage_code = f"set_random_seed({question_seed})\n" + sage_code

            # Écriture et exécution du code .sage temporaire
            with tempfile.NamedTemporaryFile("w", suffix=".sage", delete=False) as tmp:
                tmp.write(sage_code)
                tmp_name = tmp.name

            try:
                # Sauvegarde des messages en cas d'erreurs.
                result = subprocess.run(
                    ["sage", tmp_name], check=True, capture_output=True, text=True
                )
                if debug:
                    print(f"[Sage stdout]\n{result.stdout}")
                    print(f"[Sage stderr]\n{result.stderr}")
            except subprocess.CalledProcessError as e:
                stderr_output = e.stderr if e.stderr else ""
                raise SystemExit(
                    f"\n[Error generating figure for question {q['id']}]\n"
                    f"Sage stderr:\n{stderr_output}\n"
                )
            finally:
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass

        # Dépot du chemin vers la figure
        q_copy["figure"] = f"../{filename}"

    return q_copy




# --------------------------------------------------------------------
def build_exam(selected_questions, version, show_solutions, show_answers,
               seed=None, template_file="templates/default.tex", mcq_layout="choices",Title={}):
    """
    Création d'une version d'un test en LaTeX en utilisant Jinja2.
    
    Différentes options de questions sont supportées : 'tf', 'mcq' et 'open', respectivement pour vrai ou faux, choix de réponses et ouverte. Supporte également le groupement en sous-questions. Si utilisé, ceci fera en sorte que les différentes variantes d'une questions seront regroupées en (a),(b),(c), etc.
    
    Build one exam version in LaTeX using Jinja2 templating.

    Supports different question types: currently 'tf', 'open', and 'mcq'.
    Also supports grouping behavior ('none' or 'parts') for numbering style.
    When grouping == "parts", multiple variants of the same question ID
    are grouped under a single \\question with subparts (a), (b), (c).
    """
    env = Environment(
        loader=FileSystemLoader(searchpath="."),
        autoescape=False
    )
    template = env.get_template(template_file)

    # ------------------------------------------------------------
    # Pré traitement des questions et début du texte LaTeX.
    # ------------------------------------------------------------
    questions_for_template = []
    for q in selected_questions:
        qd = q.copy()
        q_type = qd["type"]  

        # Création de la base LaTeX 
        qd["question_fmt"] = Template(q["question"]).render(**q)
        if "solution" in q:
            qd["solution_fmt"] = Template(q["solution"]).render(**q)
        if "figure" in q:
            qd["figure_fmt"] = q["figure"]

        # ------------------------------------------------------------
        # questions vrai ou faux
        # ------------------------------------------------------------
        if q_type == "tf":
            qd["options_fmt"] = ["True", "False"]
            ans_val = qd.get("answer", False)
            qd["answer_fmt"] = "True" if ans_val else "False"

        # ------------------------------------------------------------
        # questions choix multiples
        # ------------------------------------------------------------
        elif q_type == "mcq":
            qd["options"] = q.get("options", [])
            #print(qd["options"])
            #qd["correct_answers"] = q.get("correct_answers", []) #Done in options data now

        # ------------------------------------------------------------
        # questions ouvertes
        # ------------------------------------------------------------
        else:
            qd["options_fmt"] = []  # pas de choix à faire
            qd["answer_fmt"] = Template(str(q.get("answer", ""))).render(**q)

        questions_for_template.append(qd)

    # ------------------------------------------------------------
    # Regroupement des questions quand l'option  grouping == "parts"
    # ------------------------------------------------------------
    grouped_questions = []
    for q in questions_for_template:
        grouping = q.get("grouping", "none")

        if grouping == "parts":
            # Début d'un nouveau groupe si c'est le premier ou un nouvel identifiant
            if not grouped_questions or grouped_questions[-1]["id"] != q["id"]:
                # Première sous-question
                q_group = q.copy()
                q_group["subquestions"] = [q]
                grouped_questions.append(q_group)
            else:
                # Ajout de la sous-question au groupement
                grouped_questions[-1]["subquestions"].append(q)
        else:
            # Sans groupement, on ajoute la question comme elle est.
            grouped_questions.append(q)
    author=Title["author"]
    title=Title["title"]
    date=Title["date"]
    # ------------------------------------------------------------
    # Création du LaTeX
    # ------------------------------------------------------------
    tex = template.render(
        version=version,
        seed=seed if seed is not None else "-",
        questions=grouped_questions,
        show_answers=show_answers,
        show_solutions=show_solutions,
        mcq_layout=mcq_layout,
        author=author,
        title=title,
        date=date
    )

    return tex






# --------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", nargs=1, required=True, help="Subcategory of questions defined in config.yaml (e.g., 'diff', 'lin_alg')",)
    parser.add_argument("--versions", type=int, default=1)
    parser.add_argument("--solutions", action="store_true")
    parser.add_argument("--answers", action="store_true")
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--usecache", action="store_true", help="Use cached parameter values and figures if available")
    parser.add_argument("--seed", type=int, default=None, help="Override all other seed settings")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    # --- Lecture du fichier de configuration ---
    config_file = "config.yaml"
    if os.path.exists(config_file):
        with open(config_file) as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}
    #Obtention de la dernière seed utilisée. Défaut à 12345 si inexistante.
    last_seed = config.get("last_seed", 12345)
    # Lecture de la mise en page souhaitée pour les questions choix multiples.
    mcq_layout = config.get("mcq_layout", "choices")

    # --- Déterminer le seed ---
    if args.seed is not None:
        seed = args.seed
    elif args.usecache:
        # Réutilise le dernier seed
        seed = last_seed
    else:
        # Générer un nouveau seed.
        random.seed()
        seed = random.randint(1, 100000)
        config["last_seed"] = seed
        with open(config_file, "w") as f:
            yaml.safe_dump(config, f,sort_keys=False)
    # Donner le seed utilisé à Python
    random.seed(seed)

    # --- Chargement du test à utiliser---
    subcategory = args.questions[0]
    if subcategory not in config.get("questions", {}):
        raise SystemExit(
        f"Subcategory '{subcategory}' not found in config.yaml. "
        f"Available subcategories: {list(config.get('questions', {}).keys())}"
        )
    test_config = copy.deepcopy(config.get("questions", {}).get(subcategory, {}))
    selected = load_questions(test_config,seed)
    author=config.get("author",{})
    title=config.get("title",{})
    date=config.get("date","\\today")
    Title={"author":author,"title":title, "date":date}
# --- Construction des versions ---
    for v in range(1, args.versions + 1):
        questions = selected[:]
        if args.shuffle:
            random.shuffle(questions)

        rendered_questions = [
            render_question(q, version=v, seed=seed, debug=args.debug, usecache=args.usecache)
            for q in questions
        ]

        tex = build_exam(
            rendered_questions,
            version=v,
            show_solutions=args.solutions,
            show_answers=args.answers,
            seed=seed,
            template_file="templates/default.tex",
            mcq_layout=mcq_layout,
            Title=Title
        )


        outdir = "output"
        os.makedirs(outdir, exist_ok=True)
        outfile = os.path.join(outdir, f"quiz_v{v}.tex")
        with open(outfile, "w") as f:
            f.write(tex)
        print(f"Wrote {outfile}")


if __name__ == "__main__":
    main()
