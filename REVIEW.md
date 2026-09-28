# Reviewing a change to verified-autonomy

Run `bash selftest.sh`. It must end `SELF-TEST PASSED`; `NOTRUN` means a dependency is
missing, not that the change is fine.

Then check the diff for these, in order:

1. **A gate that cannot fail.** Every new or changed gate has a control it must catch. If you
   can revert the fix and the suite stays green, the control is not testing it.
2. **A silent pass.** Missing, unreadable or empty config, a helper that is absent, a probe that
   times out: each must refuse, never report green.
3. **An expectation read from the subject.** A check whose expected set comes from the file it
   checks goes green when that file shrinks.
4. **A deny rule that blocks routine work.** New patterns in `hooks/deny-dangerous.sh` are
   tested against the ordinary form of the same command, not only the dangerous one.
5. **Size.** A change should read in one sitting. Comments explaining what code does, and
   controls beyond three per gate, are review cost without coverage.
