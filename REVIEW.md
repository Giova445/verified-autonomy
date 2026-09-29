# Reviewing a change to verified-autonomy

Run `bash selftest.sh`. It must end `SELF-TEST PASSED`. `NOTRUN` means a dependency is missing,
not that the change is fine.

Then check the diff, in order:

1. **A check that cannot fail.** Every new or changed rule has a control it must catch. If you
   can revert the fix and the suite stays green, the control tests nothing.
2. **A silent pass.** Missing, unreadable or empty config, an absent helper, a probe that times
   out: each must refuse or say CANNOT RUN, never report green.
3. **An expectation read from the subject.** A check whose expected values come from the code
   it checks goes green when that code shrinks.
4. **A deny rule that blocks routine work.** Test a new pattern against the ordinary form of the
   same command, not only the dangerous one.
5. **A claim the code does not back.** Every sentence in the README, a skill or a hook message
   names behavior you can find in the code.
6. **Size.** Prefer the diff that deletes. Comments that explain what code does, and controls
   beyond three per rule, cost review time and add no coverage.
