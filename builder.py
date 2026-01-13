#!/usr/bin/env python3
import argparse
import glob
import os
import random
import subprocess
import tempfile
import yaml
import json
import copy
from jinja2 import Environment, FileSystemLoader, Template

# --------------------------------------------------------------------
def load_questions(test_config, seed=None):
    """
    Load only the questions/variants specified in test_config.

    test_config: dict specifying which questions and variants to include.
    seed: int or None. If provided, ensures deterministic random selection
          when choose < len(pool).
    """
    rng = random.Random(seed) if seed is not None else random
    all_questions = []
    for qid, rules in test_config.items():
        qfile = f"questions/{qid}.yaml"
        if not os.path.exists(qfile):
            raise SystemExit(f"Missing question file: {qfile}")

        try:
            with open(qfile, "r") as f:
                qdata = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise SystemExit(
                f"\nYAML parse error in {qfile}:\n{e}\n"
                "Hint: In double-quoted YAML strings, escape LaTeX backslashes like \\\\sin, \\\\pi, \\\\frac, etc."
            )

        # Get all variants
        if "variants" not in qdata or not qdata["variants"]:
            raise SystemExit(
                f"Question file {qfile} must define a non-empty 'variants' list."
            )

        pool = []
        for var in qdata["variants"]:
            if "sub_id" not in var:
                raise SystemExit(f"Variant in {qfile} is missing required 'sub_id'.")
            q_variant = {**qdata, **var}
            q_variant["id"] = qdata["id"]
            q_variant.pop("variants", None)
            pool.append(q_variant)

        # --- DEBUG: show pool of sub_ids ---
        #print(f"[DEBUG] Question {qid} pool of sub_ids: {[v['sub_id'] for v in pool]}")

        # Apply selection rules
        select_spec = rules.get("select", "all")
        choose_spec = rules.get("choose", None)

        # ------------------------------------------------------------
        # NEW: grouping, group_text, and n_wrong control
        # ------------------------------------------------------------
		# These are optional in config and default to 'none' (no grouping)
        # and an empty group_text (no intro line).
        grouping = rules.get("grouping", "none")
        group_text = rules.get("group_text", "")
        n_wrong = rules.get("n_wrong", None)

        # --- DEBUG: show select/choose spec ---
        #print(f"[DEBUG] Question {qid} select_spec: {select_spec}, choose_spec: {choose_spec}")

        if select_spec == "all":
            selected = pool
        else:
            selected = [v for v in pool if v["sub_id"] in select_spec]

        # --- DEBUG: show selected after filtering ---
        #print(f"[DEBUG] Question {qid} selected after filtering: {[v['sub_id'] for v in selected]}")

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
        # Attach config-level attributes (grouping + group_text + n_wrong)
        # ------------------------------------------------------------
        for q in chosen:
            q["grouping"] = grouping
            q["group_text"] = group_text
            q["n_wrong"] = n_wrong

        all_questions.extend(chosen)

    return all_questions
# --------------------------------------------------------------------
def run_sage_code(code, debug=False, seed=None):
    """Run a small Sage snippet that defines variables for LaTeX templating.
    Returns a dict of basic Python types only (int, float, str, bool).
    """
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
    Render one question: handle per-question seeded generate_params and generate_figure.

    Supported types:
      - open
      - tf
      - mcq
    """
    q_copy = q.copy()

    # ------------------------------------------------------------
    # Get type of question (default: open-ended)
    # ------------------------------------------------------------
    q_copy["type"] = q.get("type", "open")

    # Path to the cache file inside a dedicated cache folder
    cache_folder = "cache"
    os.makedirs(cache_folder, exist_ok=True)
    cache_file = os.path.join(cache_folder, "seeds_cache.yaml")

    # Load cache if it exists
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            cache = yaml.safe_load(f) or {}
    else:
        cache = {}

    # Derive a deterministic per-question, per-version seed
    if seed is not None:
        question_seed = seed + (hash(q["id"]) % 10000)+(hash(q["sub_id"]) % 10000) + version
        #print(question_seed)
    else:
        question_seed = None

    # Check if we can use cached parameters
    cache_key = f"{q['id']}_variante{q['sub_id']}_version{version}"
    if usecache and cache_key in cache:
        # Retrieve cached parameter values
        q_copy.update(cache[cache_key])
    else:
        # Handle random parameters with Sage using the per-question seed
        if "generate_params" in q and q["generate_params"]:
            local_vars = run_sage_code(
                q["generate_params"], debug=debug, seed=question_seed
            )
            q_copy.update(local_vars)
            # Save to cache
            cache[cache_key] = local_vars
            with open(cache_file, "w") as f:
                yaml.safe_dump(cache, f)

    # ------------------------------------------------------------
    # MCQ preprocessing (choice selection + shuffling)
    # ------------------------------------------------------------
    if q_copy["type"] == "mcq":
        # Normalize correct answers to a list
        correct = q.get("answer", [])
        if not isinstance(correct, list):
            correct = [correct]

        wrong = q.get("wrong_ans", [])
        n_wrong = q.get("n_wrong", None)

        # Limit number of wrong answers if requested
        if n_wrong is not None and n_wrong < len(wrong):
            rng = random.Random(question_seed) if question_seed is not None else random
            wrong = rng.sample(wrong, n_wrong)

        # Combine and shuffle all options deterministically
        options = []
        for ans in correct:
            options.append({"text": ans, "is_correct": True})
        for ans in wrong:
            options.append({"text": ans, "is_correct": False})

        rng = random.Random(question_seed) if question_seed is not None else random
        rng.shuffle(options)

        q_copy["options"] = options

    # ------------------------------------------------------------
    # Handle figure generation (use Jinja2 to render the Sage code)
    # ------------------------------------------------------------
    if "generate_figure" in q and q["generate_figure"]:
        filename = f"figures/{q['id']}_variante{q['sub_id']}_version{version}.png"
        os.makedirs("figures", exist_ok=True)

        # Make the filename available to the figure template
        q_copy["filename"] = filename

        # Only generate figure if not using cache or figure file missing
        if not (usecache and os.path.exists(filename)):
            # Render the figure code with Jinja2 so {{var}} is substituted safely
            sage_template = Template(q["generate_figure"])
            sage_code = sage_template.render(**q_copy)

            # Ensure the Sage process uses the same per-question seed (if present)
            if question_seed is not None:
                sage_code = f"set_random_seed({question_seed})\n" + sage_code

            # Write and run the temporary .sage script
            with tempfile.NamedTemporaryFile("w", suffix=".sage", delete=False) as tmp:
                tmp.write(sage_code)
                tmp_name = tmp.name

            try:
                # Always capture text output so we can show errors cleanly
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

        # Store figure path for LaTeX (use relative-up path as before)
        q_copy["figure"] = f"../{filename}"

    return q_copy




# --------------------------------------------------------------------
def build_exam(selected_questions, version, show_solutions, show_answers,
               seed=None, template_file="templates/default.tex", mcq_layout="choices"):
    """
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
    # Preprocess questions and render text
    # ------------------------------------------------------------
    questions_for_template = []
    for q in selected_questions:
        qd = q.copy()
        q_type = qd["type"]  # already normalized in render_question

        # Base LaTeX rendering using Jinja2 for question text and optional fields
        qd["question_fmt"] = Template(q["question"]).render(**q)
        if "solution" in q:
            qd["solution_fmt"] = Template(q["solution"]).render(**q)
        if "figure" in q:
            qd["figure_fmt"] = q["figure"]

        # ------------------------------------------------------------
        # TRUE/FALSE questions
        # ------------------------------------------------------------
        if q_type == "tf":
            qd["options_fmt"] = ["True", "False"]
            ans_val = qd.get("answer", False)
            qd["answer_fmt"] = "True" if ans_val else "False"

        # ------------------------------------------------------------
        # MULTIPLE-CHOICE questions
        # ------------------------------------------------------------
        elif q_type == "mcq":
            # Options already shuffled in render_question
            qd["options"] = q.get("options", [])
            print(qd["options"])
            #qd["correct_answers"] = q.get("correct_answers", []) #Done in options data now

        # ------------------------------------------------------------
        # OPEN questions (and all others for now)
        # ------------------------------------------------------------
        else:
            qd["options_fmt"] = []  # no choices to list
            qd["answer_fmt"] = Template(str(q.get("answer", ""))).render(**q)

        questions_for_template.append(qd)

    # ------------------------------------------------------------
    # Group questions when grouping == "parts"
    # ------------------------------------------------------------
    grouped_questions = []
    for q in questions_for_template:
        grouping = q.get("grouping", "none")

        if grouping == "parts":
            # Start a new grouped question if this is the first or a new ID
            if not grouped_questions or grouped_questions[-1]["id"] != q["id"]:
                # Initialize the group container with its first subquestion
                q_group = q.copy()
                q_group["subquestions"] = [q]
                grouped_questions.append(q_group)
            else:
                # Add additional subquestion to the last group
                grouped_questions[-1]["subquestions"].append(q)
        else:
            # Non-grouped question: append as is
            grouped_questions.append(q)

    # ------------------------------------------------------------
    # Render LaTeX
    # ------------------------------------------------------------
    tex = template.render(
        version=version,
        seed=seed if seed is not None else "-",
        questions=grouped_questions,
        show_answers=show_answers,
        show_solutions=show_solutions,
        mcq_layout=mcq_layout,
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

    # --- Config setup ---
    config_file = "config.yaml"
    if os.path.exists(config_file):
        with open(config_file) as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    last_seed = config.get("last_seed", 12345)
    # Load optional MCQ layout
    mcq_layout = config.get("mcq_layout", "choices")

    # --- Determine seed ---
    if args.seed is not None:
        seed = args.seed
    elif args.usecache:
        # Reuse last seed
        seed = last_seed
    else:
        # Generate a fresh seed
        random.seed()
        seed = random.randint(1, 100000)
        config["last_seed"] = seed
        with open(config_file, "w") as f:
            yaml.safe_dump(config, f,sort_keys=False)
    # Seed Python's RNG for reproducibility
    random.seed(seed)

    # --- Load selected subcategory of questions ---
    subcategory = args.questions[0]
    if subcategory not in config.get("questions", {}):
        raise SystemExit(
        f"Subcategory '{subcategory}' not found in config.yaml. "
        f"Available subcategories: {list(config.get('questions', {}).keys())}"
        )
    test_config = copy.deepcopy(config.get("questions", {}).get(subcategory, {}))
    selected = load_questions(test_config,seed)
# --- Build versions ---
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
        )


        outdir = "output"
        os.makedirs(outdir, exist_ok=True)
        outfile = os.path.join(outdir, f"quiz_v{v}.tex")
        with open(outfile, "w") as f:
            f.write(tex)
        print(f"Wrote {outfile}")


if __name__ == "__main__":
    main()
