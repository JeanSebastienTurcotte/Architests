#!/usr/bin/env python3
import argparse
import glob
import os
import random
import subprocess
import tempfile
import yaml
import json

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
def run_sage_code(code, debug=False):
    """Run a small Sage snippet that defines variables for LaTeX templating.
    Returns a dict of basic Python types only (int, float, str, bool).
    """
    sage_script = f"""
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
    """Render one question: handle generate_params and generate_figure."""
    q_copy = q.copy()

    # Handle random parameters with Sage
    if "generate_params" in q and q["generate_params"]:
        local_vars = run_sage_code(q["generate_params"], debug=debug)
        q_copy.update(local_vars)

    # Handle figure generation
    if "generate_figure" in q and q["generate_figure"]:
        filename = f"figures/{q['id']}_v{version}.png"
        os.makedirs("figures", exist_ok=True)
        sage_code = f"""
filename = "{filename}"
{q['generate_figure'].format(**q_copy)}
"""
        with tempfile.NamedTemporaryFile("w", suffix=".sage", delete=False) as tmp:
            tmp.write(sage_code)
            tmp_name = tmp.name

        try:
            subprocess.run(["sage", tmp_name], check=True, capture_output=debug)
        except subprocess.CalledProcessError as e:
            raise SystemExit(
                f"\n[Error generating figure for question {q['id']}]\n"
                f"Sage stderr:\n{e.stderr.decode()}\n"
            )
        finally:
            os.remove(tmp_name)

        q_copy["figure"] = f"../{filename}"

    return q_copy

# --------------------------------------------------------------------
def build_exam(selected_questions, version, show_solutions, show_answers):
    header = [
        "\\documentclass[12pt]{exam}",
        "\\usepackage{graphicx}",
        "\\begin{document}",
        f"\\section*{{Version {version}}}",
        "\\begin{questions}",
    ]

    body = []
    for q in selected_questions:
        # Substitute variables in question, answer, solution
        question_text = q["question"].format(**q)
        body.append("\\question " + question_text)

        if "figure" in q:
            body.append(f"\\includegraphics[width=0.5\\linewidth]{{{q['figure']}}}")

        if "parts" in q:
            body.append("\\begin{parts}")
            for part in q["parts"]:
                part_text = part["text"].format(**q)
                body.append("\\part " + part_text)
                if show_answers and "answer" in part:
                    body.append("\\\\ Answer: " + part["answer"].format(**q))
                if show_solutions and "solution" in part:
                    body.append("\\\\ Solution: " + part["solution"].format(**q))
            body.append("\\end{parts}")
        else:
            if show_answers and "answer" in q:
                body.append("\\\\ Answer: " + q["answer"].format(**q))
            if show_solutions and "solution" in q:
                body.append("\\\\ Solution: " + q["solution"].format(**q))

    footer = ["\\end{questions}", "\\end{document}"]

    return "\n".join(header + body + footer)

# --------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", nargs="+", default=["all"], help="IDs of questions or 'all'")
    parser.add_argument("--versions", type=int, default=1)
    parser.add_argument("--solutions", action="store_true")
    parser.add_argument("--answers", action="store_true")
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

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

        rendered_questions = [render_question(q, version=v, seed=args.seed, debug=args.debug) for q in questions]

        tex = build_exam(
            rendered_questions,
            version=v,
            show_solutions=args.solutions,
            show_answers=args.answers,
        )

        outdir = "output"
        os.makedirs(outdir, exist_ok=True)
        outfile = os.path.join(outdir, f"quiz_v{v}.tex")
        with open(outfile, "w") as f:
            f.write(tex)
        print(f"Wrote {outfile}")


if __name__ == "__main__":
    main()
