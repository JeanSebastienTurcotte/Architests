#!/usr/bin/env python3
import argparse
import glob
import os
import random
import subprocess
import tempfile
import yaml
import json
from jinja2 import Environment, FileSystemLoader, Template

# --------------------------------------------------------------------
def load_questions():
    question_files = glob.glob("questions/*.yaml")
    all_questions = []

    for qf in question_files:
        try:
            with open(qf, "r") as f:
                qdata = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise SystemExit(
                f"\nYAML parse error in {qf}:\n{e}\n"
                "Hint: In double-quoted YAML strings, escape LaTeX backslashes like \\\\sin, \\\\pi, \\\\frac, etc."
            )
        all_questions.append(qdata)

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

def render_question(q, version, seed=None, debug=False):
    """Render one question: handle per-question seeded generate_params and generate_figure."""
    q_copy = q.copy()

    # Derive a deterministic per-question, per-version seed
    if seed is not None:
        question_seed = seed + (hash(q["id"]) % 10000) + version
    else:
        question_seed = None

    # Handle random parameters with Sage using the per-question seed
    if "generate_params" in q and q["generate_params"]:
        local_vars = run_sage_code(q["generate_params"], debug=debug, seed=question_seed)
        q_copy.update(local_vars)

    # Handle figure generation (use Jinja2 to render the Sage code)
    from jinja2 import Template

	# Inside render_question, for generate_figure:										  
    if "generate_figure" in q and q["generate_figure"]:
        filename = f"figures/{q['id']}_v{version}.png"
        os.makedirs("figures", exist_ok=True)

        # Make the filename available to the figure template
        q_copy["filename"] = filename

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
def build_exam(selected_questions, version, show_solutions, show_answers, seed=None, template_file="templates/default.tex"):
    env = Environment(
        loader=FileSystemLoader(searchpath="."),
        autoescape=False
    )
    template = env.get_template(template_file)

    questions_for_template = []
    for q in selected_questions:
        qd = q.copy()
        # Render LaTeX text using Jinja2
        qd["question_fmt"] = Template(q["question"]).render(**q)
        if "answer" in q:
            qd["answer_fmt"] = Template(q["answer"]).render(**q)
        if "solution" in q:
            qd["solution_fmt"] = Template(q["solution"]).render(**q)
        if "figure" in q:
            qd["figure_fmt"] = q["figure"]
        questions_for_template.append(qd)

    tex = template.render(
        version=version,
        seed=seed if seed is not None else "-",
        questions=questions_for_template,
        show_answers=show_answers,
        show_solutions=show_solutions,
    )

    return tex



# --------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", nargs="+", default=["all"], help="IDs of questions or 'all'")
    parser.add_argument("--versions", type=int, default=1)
    parser.add_argument("--solutions", action="store_true")
    parser.add_argument("--answers", action="store_true")
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--regenerate",action="store_true",help="Reuse last seed from config instead of generating new parameters")
    parser.add_argument("--seed", type=int, default=None, help="Override all other seed settings")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

																	  
    # Load last seed from config
    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    last_seed = config.get("last_seed", 12345)

    # Determine seed
    if args.seed is not None:
        seed = args.seed
    elif args.regenerate:
        random.seed()
        seed = random.randint(1, 100000)
        # Update last_seed in config
        config["last_seed"] = seed
        with open("config.yaml", "w") as f:
            yaml.safe_dump(config, f)
    else:
        seed = last_seed

# Seed Python's random for reproducibility in builder												 
    random.seed(seed)


    all_questions = load_questions()

	# Pick which questions					  
    if args.questions == ["all"]:
        selected = all_questions
    else:
        selected = [q for q in all_questions if q["id"] in args.questions]

    for v in range(1, args.versions + 1):
        questions = selected[:]
        if args.shuffle:
            random.shuffle(questions)

        rendered_questions = [render_question(q, version=v, seed=seed, debug=args.debug) for q in questions]

        tex = build_exam(
            rendered_questions,
            version=v,
            show_solutions=args.solutions,
            show_answers=args.answers,
            seed=seed,
        )

        outdir = "output"
        os.makedirs(outdir, exist_ok=True)
        outfile = os.path.join(outdir, f"quiz_v{v}.tex")
        with open(outfile, "w") as f:
            f.write(tex)
        print(f"Wrote {outfile}")


if __name__ == "__main__":
    main()
