#!/usr/bin/env python3
"""The eval and control types.

An EVAL is a task+check pair, in the Stage 4b sense:

  prompt   the configuration change an agent could plausibly be asked to make. It is
           documentation of what this eval defends against — the checks below do NOT
           invoke a model, and none of them need to. A deterministic assertion over the
           configuration is strictly stronger evidence than a sampled model run: it is
           reproducible, it costs nothing, and it cannot be flaky.
  check    check(root) -> list of findings. EMPTY LIST MEANS PASS. Any string in the list
           is a defect, printed verbatim.

A CONTROL is the proof that the check can fail. It breaks exactly one thing in a copy of
the tree and asserts the check then produces a NEW finding containing `token`. A check
that passes the clean tree proves nothing on its own — one that returns [] unconditionally
passes the clean tree too.
"""


class Control:
    """One deliberate manipulation of a fixture, and what the check must then say.

    expect:
      "fail"  the check must produce a NEW finding containing `token`. This is the
              positive control: proof the check can detect the thing it looks for.
      "pass"  the check must produce NO findings. Proof the check is not unconditionally
              red — a check that always fails detects nothing either, it just looks
              like it does. `token` is ignored.

    fixture:
      "tree"  copy the whole repo, then manipulate the copy
      "empty" start from an empty directory, for a check that reads exactly one path:
              an empty fixture holds constant everything such a check can observe

    setup:
      optional. Runs BEFORE the baseline is taken, to establish the precondition under
      which the property is testable at all. It is fixture preparation, not a second
      manipulation: the baseline is measured after it, so exactly one thing still varies
      between baseline and result — whatever `apply` did.
    """

    def __init__(self, name, apply, token="", fixture="tree", expect="fail", setup=None):
        if expect not in ("fail", "pass"):
            raise ValueError(f"{name}: expect must be 'fail' or 'pass'")
        if expect == "fail" and not token:
            raise ValueError(f"{name}: a failing control needs a token naming the break")
        self.name = name
        self.apply = apply
        self.token = token
        self.fixture = fixture
        self.expect = expect
        self.setup = setup


class Eval:
    def __init__(self, eval_id, prompt, why, check, controls):
        if not controls:
            raise ValueError(f"{eval_id}: an eval with no control is not an eval")
        self.id = eval_id
        self.prompt = prompt
        self.why = why
        self.check = check
        self.controls = controls
