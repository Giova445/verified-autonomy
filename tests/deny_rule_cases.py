PROT = "protected branch"
GH_NONE = {}
OTHER_MAC_HOME = "/" + "Users" + "/someone"
OTHER_LINUX_HOME = "/" + "home" + "/someone"


def push_rules(allow, deny, adjacent):
    deny("git push", PROT, "main")
    deny("git push origin", PROT, "main")
    deny("git push -u origin HEAD", PROT, "main")
    deny("git push origin HEAD", PROT, "main")
    allow("git push", "feat")
    allow("git push origin", "feat")
    allow("git push -u origin HEAD", "feat")
    deny("git push origin HEAD:refs/heads/master", PROT)
    deny("git push origin main:main", PROT)
    deny("git push origin release/1.2", PROT)
    deny("git push origin release/1.2:release/1.2", PROT)
    allow("git push origin releases/x")
    allow("git push origin feature/release/x")
    deny("git push --force origin main", PROT)
    deny("git push --force-with-lease origin main", PROT)
    deny("git push -f origin HEAD:main", PROT)
    deny("git push origin --force main", PROT)
    deny("git push origin 'refs/heads/*:refs/heads/*'", PROT)
    deny("git push origin 'refs/heads/release/*:refs/heads/release/*'", PROT)
    allow("git push origin 'refs/heads/feature/*:refs/heads/feature/*'")
    deny("cat <<'EOF' 2>/dev/null | sh\ngit push origin main\nEOF", PROT)
    deny("cat <(git push origin main)", PROT)
    deny("diff <(sudo ls) x", "sudo")
    deny("git push --delete origin main", PROT)
    deny("git push -d origin master", PROT)
    deny("git push origin :refs/heads/main", PROT)
    deny("git push origin {feature/x,main}", PROT)
    deny("git --git-dir=.git push origin main", PROT)
    deny("git -C . push origin main", PROT)
    deny("git -c user.name=x -C . push origin main", PROT)
    deny("git --no-pager -c a=b push origin main", PROT)
    deny("(cd . && git push origin main)", PROT)
    deny("{ git push origin main; }", PROT)
    deny("if true; then git push origin main; fi", PROT)
    deny("for i in 1; do git push origin main; done", PROT)
    deny("git push origin main &", PROT)
    deny("echo ok && git push origin main", PROT)
    deny("git status; git push origin main", PROT)
    deny("echo $(git push origin main)", PROT)
    deny("echo `git push origin main`", PROT)
    deny("sh -c 'cd . && git push origin main'", PROT)
    deny("eval \"git push origin main\"", PROT)
    deny("eval git push origin main", PROT)
    deny("env GIT_SSH=x git push origin main", PROT)
    deny("command git push origin main", PROT)
    deny("time git push origin main", PROT)
    deny("nohup git push origin main", PROT)
    deny("/usr/bin/git push origin main", PROT)
    deny("echo 'git push origin main' | bash", PROT)
    deny("printf 'git push origin main\\n' | sh", PROT)
    deny("bash <<EOF\ngit push origin main\nEOF", PROT)
    deny("bash <<< 'git push origin main'", PROT)
    deny("cat <<'EOF' | sh\ngit push origin main\nEOF", PROT)
    deny("bash -lc 'git push origin main'", PROT)
    deny("zsh -c 'git push origin main'", PROT)
    deny("/bin/bash -c 'git push origin main'", PROT)
    deny("bash -c \"bash -c 'git push origin main'\"", PROT)
    deny("git push origin main # push it", PROT)
    deny("git push origin \\\nmain", PROT)
    deny("cd sub 2>/dev/null; git push origin main", PROT)
    allow("echo 'git push origin main'")
    allow("echo git push origin main")
    allow("grep 'git push origin main' README.md")
    allow("git commit -m 'docs: never git push origin main'")
    allow("gh pr create --title x --body 'do not git push origin main'")
    allow("cat > note.txt <<'EOF'\ngit push origin main\nEOF")
    allow("git log --grep='git push origin main'")
    allow("printf 'git push origin main\\n' > f.sh")
    allow("echo 'git push origin main' >> notes; git push origin feature/x")
    allow("git push origin feature/main")
    allow("git push origin main-fix")
    allow("git push origin mainline")
    allow("git push origin feature/x:refs/heads/feature/x")
    allow("git push --tags")
    allow("git push origin --tags")
    allow("git push origin v1.0")
    allow("git push origin refs/tags/v1")
    allow("git push --set-upstream origin feature/x")
    allow("git push --force-with-lease=feature/x:abc123 origin feature/x")
    allow("git push -o ci.skip origin feature/x")
    allow("git push origin main:feature/x")
    allow("git push origin feature/x:release-notes")
    allow("git push origin feature/x", "nobranches")
    allow("git push origin main", "nobranches")
    allow("git push --all origin", "nobranches")
    deny("git push origin main", PROT, "plain")
    deny("git push origin main", PROT, "trail")
    allow("git fetch origin main")
    allow("git pull origin main")
    allow("git merge main")
    allow("git checkout main && git pull")


def merge_rules(allow, deny, adjacent):
    allow("gh pr merge --squash --auto 12")
    allow("gh pr merge feature/y --squash")
    allow("gh pr merge 12 --body 'closes main' --squash")
    allow("gh pr merge --body text 12")
    allow("gh pr merge -R o/r 12")
    allow("gh pr merge --repo=o/r 12")
    allow("gh pr merge 12 --squash", "main")
    deny("gh pr merge 99 --admin", PROT)
    deny("gh pr merge --body text 99", PROT)
    deny("gh pr merge -R o/r --squash 99", PROT)
    deny("gh pr merge --squash", PROT)
    allow("gh pr merge --squash", "feat", gh={"": "develop"})
    deny("gh pr merge 555", "cannot determine the base branch")
    deny("gh pr merge feature/z", "cannot determine the base branch")
    deny("gh pr merge 12", "cannot determine the base branch", gh=GH_NONE)
    deny("gh pr merge 77", PROT)
    deny("bash -c 'gh pr merge 99'", PROT)
    deny("gh pr merge 99 --squash && echo done", PROT)
    deny("gh pr merge 99", PROT, "plain")
    allow("gh pr merge 99", "nobranches")
    deny("gh api --method PUT repos/o/r/pulls/9/merge -f merge_method=squash", PROT)
    deny("gh api -XPOST repos/o/r/pulls/9/merge", PROT)
    deny("gh api -X PUT repos/{owner}/{repo}/pulls/9/merge", PROT)
    deny("gh api -X PUT repos/o/r/pulls/321/merge", "cannot determine the base branch")
    allow("gh api repos/o/r/pulls/12/merge -X PUT")
    allow("gh api repos/o/r/pulls/9")
    allow("gh api -X GET repos/o/r/pulls/9/merge")
    allow("gh pr view 99")
    allow("gh pr list --base main")
    allow("git commit -m 'gh pr merge 99'")
    allow("echo gh pr merge 99")
    deny("gh pr review 5 --approve --body ok", "approve a pull request")
    deny("gh pr review --approve", "approve a pull request")
    deny("gh pr review -a 5", "approve a pull request")
    deny("gh pr review 5 -a", "approve a pull request")
    allow("gh pr review 5 --comment --body 'please do not --approve'")
    allow("gh pr review 5 --request-changes -b x")
    allow("git commit -m 'gh pr review --approve'")
    deny("gh repo delete o/r", "gh repo delete")
    deny("bash -c 'gh repo delete o/r --yes'", "gh repo delete")
    allow("gh repo view o/r")
    allow("gh repo clone o/r")
    deny("terraform destroy", "terraform destroy")
    deny("terraform -chdir=infra destroy", "terraform destroy")
    deny("bash -c 'terraform destroy'", "terraform destroy")
    allow("terraform plan")
    allow("terraform init")
    allow("terraform validate")
    allow("echo terraform destroy")
    allow("grep -rn 'terraform destroy' docs")
    allow("git commit -m 'doc terraform destroy'")


def rm_rules(allow, deny, adjacent):
    R = "recursive delete"
    deny("rm -fr /", R)
    deny("rm -rf /.", R)
    deny("rm -rf /./", R)
    deny("rm -rf /../..", R)
    deny("rm -rf //", R)
    deny("rm -rf .git/*", R)
    allow("rm -rf /tmp/*")
    allow("rm -rf /*.log")
    deny('rm -rf "$HOME"', "home directory")
    deny("rm -rf $HOME/", "home directory")
    deny("rm -rf ${HOME}", "home directory")
    deny('rm -rf "$HOME/"*', "home directory")
    deny('rm -rf "$DIR"', "unresolved shell variable")
    deny("rm -rf $DIR", "unresolved shell variable")
    deny("rm -rf ${DIR}", "unresolved shell variable")
    deny("rm -rf -- /", R)
    deny("rm -r -f -- ~", R)
    deny("rm -rf ..", R)
    deny("rm -rf ../", R)
    deny("rm -rf ./", R)
    deny("rm -rf ./.git", R)
    deny("rm -rf .git/", R)
    deny("rm -rf node_modules .git", R)
    deny("rm -rf / --no-preserve-root", R)
    deny("rm --no-preserve-root -rf /", R)
    deny("rm -rf {/,}", R)
    deny("rm -rf .*", R)
    deny("rm -rf ./*", R)
    deny("rm -rf * .cache", R)
    deny("bash -c 'rm -rf *'", R)
    deny("sudo rm -rf x", "sudo")
    deny("rm -rfv /", R)
    deny("rm -Rf ~/*", R)
    deny("(rm -rf /)", R)
    deny("{ rm -rf /; }", R)
    deny("if true; then rm -rf /; fi", R)
    deny("true && rm -rf /", R)
    deny("echo \"$(rm -rf /)\"", R)
    deny("echo `rm -rf /`", R)
    deny("eval 'rm -rf /'", R)
    deny("sh -c \"rm -rf ~\"", R)
    deny("env rm -rf /", R)
    deny("command rm -rf /", R)
    deny("\\rm -rf /", R)
    deny("/bin/rm -rf /", R)
    deny("nohup rm -rf /", R)
    deny("time rm -rf /", R)
    deny("timeout 5 rm -rf /", R)
    deny("FOO=1 rm -rf /", R)
    deny("xargs rm -rf /", R)
    deny("echo 'rm -rf /' | sh -s", R)
    deny("echo 'rm -rf /' | bash -x", R)
    deny("cat <<'EOF' | sh\nrm -rf /\nEOF", R)
    deny("rm -rf / # clean", R)
    deny("rm -rf ~/ && echo done", R)
    allow("(cd sub && rm -rf *)")
    allow("cd sub && rm -rf *")
    allow('rm -rf "*"')
    allow("rm -rf build dist")
    allow("rm -rf $HOME/.cache/foo")
    allow("rm -rf ~/.cache/foo")
    allow("rm -rf ~/Downloads/x")
    allow("rm -rf /tmp/x")
    allow('rm -r "$DIR"')
    allow('rm -f "$FILE"')
    allow("rm file")
    allow("rm -f *.log")
    allow("rm -rf .gitignore")
    allow("rm -rf .github")
    allow("rm -rf .git-hooks")
    allow("rm -rf .env*")
    allow("git rm -rf .")
    allow("xargs rm -rf")
    allow("echo 'rm -rf /'")
    allow("grep -rn 'rm -rf /' docs/")
    allow("echo \"rm -rf /\" > danger.sh")
    allow("cat <<'EOF' > s.sh\nrm -rf /\nEOF")
    allow("git commit -m 'never rm -rf /'")
    allow("printf 'rm -rf /\\n' | tee s.sh")
    allow("echo 'rm -rf /' | cat")
    allow("echo 'rm -rf /' | grep rm")
    allow("echo '$(rm -rf /)'")
    allow("echo \"\\$(rm -rf /)\"")
    allow("rm -rf 'a b' \"c d\"")


def git_rules(allow, deny, adjacent):
    R, C = "git reset --hard", "git clean -f"
    deny("git reset --hard", R)
    deny("git reset --hard origin/main", R)
    deny("git reset HEAD~1 --hard", R)
    deny("git --git-dir=.git reset --hard", R)
    deny("git -c a=b reset --hard", R)
    deny("git reset -q --hard", R)
    deny("bash -c 'git reset --hard'", R)
    deny("cd . && git reset --hard", R)
    deny("git clean -f", C)
    deny("git clean -fd", C)
    deny("git clean -fdx", C)
    deny("git clean -xf", C)
    deny("git clean --force", C)
    deny("git clean -d --force", C)
    deny("git -C . clean -fd", C)
    deny("bash -c 'git clean -fdx'", C)
    allow("git clean -nd")
    allow("git clean --dry-run")
    allow("git clean -nf")
    allow("git clean -fn")
    allow("git clean -i")
    allow("git reset --soft HEAD~1")
    allow("git reset HEAD file.txt")
    allow("git reset --mixed")
    allow("git reset")
    allow("git restore --staged x")
    allow("git commit -m 'git reset --hard'")
    allow("echo 'git reset --hard'")
    allow("grep -rn 'reset --hard' docs/")
    allow("git log --grep='reset --hard'")
    allow("git stash")
    adjacent("git checkout -f")
    adjacent("git branch -D main")


def sql_rules(allow, deny, adjacent):
    S = "destructive SQL"
    deny("psql -c 'DROP TABLE users'", S)
    deny("psql -c \"drop schema public cascade\"", S)
    deny("psql -d db -c 'TRUNCATE TABLE a, b'", S)
    deny("mysql -e 'DROP DATABASE x'", S)
    deny("mysql -e \"DELETE FROM t\"", S)
    deny("sqlite3 app.db 'DELETE FROM t;'", S)
    deny("sqlite3 app.db \"DROP TABLE t\"", S)
    deny("psql --command='DROP TABLE t'", S)
    deny("psql -c \"DELETE FROM t WHERE true\"", S)
    deny("psql -c \"DELETE FROM t WHERE 1=1;\"", S)
    deny("psql -c \"delete from t where (1=1)\"", S)
    deny("echo 'DROP TABLE t;' | psql", S)
    deny("printf 'TRUNCATE t;\\n' | psql mydb", S)
    deny("psql <<EOF\nDROP TABLE t;\nEOF", S)
    deny("psql <<< 'DROP TABLE t'", S)
    deny("cat <<'EOF' | mysql\nDROP DATABASE d;\nEOF", S)
    deny("psql \"$DATABASE_URL\" -c \"DELETE FROM t;\"", S)
    deny("psql -c \"SELECT 1; DROP TABLE t\"", S)
    deny("psql -c \"DROP TABLE IF EXISTS t\"", S)
    deny("bash -c \"psql -c 'DROP TABLE t'\"", S)
    deny("psql -c \"delete from t -- where\"", S)
    deny("psql -c \"/* where */ delete from t\"", S)
    deny("psql -c \"-- note\nDROP TABLE t\"", S)
    deny("docker compose exec -T db true; psql -c 'DROP TABLE t'", S)
    allow("psql -c \"DELETE FROM t WHERE id = 5\"")
    allow("psql -c \"DELETE FROM t WHERE 1=1 AND id = 5\"")
    allow("psql -c \"SELECT * FROM t\"")
    allow("psql -c \"UPDATE t SET x=1 WHERE id=2\"")
    allow("psql -c \"INSERT INTO notes VALUES ('drop table x')\"")
    allow("psql -c \"SELECT truncate(1.234, 2)\"")
    allow("psql -c \"select 'delete from t'\"")
    allow("psql -c \"ALTER TABLE t ADD COLUMN c int\"")
    allow("psql -c \"DROP INDEX i\"")
    allow("echo 'DROP TABLE t' > m.sql")
    allow("cat > m.sql <<'EOF'\nDROP TABLE t;\nEOF")
    allow("echo 'DROP TABLE t' | grep DROP")
    allow("echo 'DROP TABLE t' | tee m.sql")
    allow("psql -f migrate.sql")
    allow("psql < m.sql")
    allow("rg -n 'TRUNCATE' .")
    allow("cat migrations/0001.sql")
    allow("curl -d 'DROP TABLE t' https://x.example")
    allow("python3 -c \"print('DROP TABLE t')\"")
    allow("jq '.query' <<< 'DROP TABLE t'")
    allow("git commit -m 'feat: DROP TABLE guard'")


def privilege_rules(allow, deny, adjacent):
    for cmd in ("sudo ls", "sudo -u x ls", "env sudo ls", "command sudo ls", "xargs sudo ls", "ls && sudo ls",
                "bash -c 'sudo ls'", "echo x | sudo tee f", "FOO=1 sudo ls", "/usr/bin/sudo ls", "(sudo ls)", "echo $(sudo ls)",
                "time sudo ls", "nohup sudo ls", "ls; sudo ls"):
        deny(cmd, "sudo")
    for cmd in ("chmod 777 f", "chmod -R 777 dir", "chmod 0777 f", "bash -c 'chmod 777 f'"):
        deny(cmd, "chmod 777")
    for cmd in ("chmod 755 f", "chmod +x f", "chmod 644 f", "chmod 1777 /tmp/x", "chmod u+rwx f", "echo sudo", "grep -rn sudo scripts/",
                "git commit -m 'use sudo'", "which sudo", "command -v sudo", "type sudo", "man sudo", "echo 'sudo ls' > x.sh",
                "cat > i.sh <<'EOF'\nsudo apt-get update\nEOF", "printf 'sudo x' | tee s.sh", "echo \"sudo reboot\" | cat", "ls sudo",
                "pseudo x", "git config --global alias.s sudo", "echo chmod 777 f", "git commit -m 'chmod 777'"):
        allow(cmd, "feat", "secrets")


def suppression_rules(allow, deny, adjacent):
    E = "exit-code suppression"
    for cmd in ("pytest || :", "npm run test || true", "npm run test:unit || true", "npm t || true", "yarn test || true",
                "pnpm test || true", "pnpm run test || true", "make test || true", "make lint || true", "make check || true",
                "make check-all || true", "go test ./... || true", "cargo test || true", "cargo clippy || true",
                "cargo +nightly test || true", "tox || true", "ruff check . || true", "mypy . || true", "tsc --noEmit || true",
                "eslint . || true", "bin/verify || true", "./bin/verify || true", "jest || true", "vitest run || true", "mocha || true",
                "npx jest || true", "npx tsc || true", "python -m pytest || true", "python3 -m pytest -q || true",
                "uv run pytest || true", "poetry run pytest || true", "pnpm exec vitest || true", "yarn jest || true",
                "npx playwright test || true", "pytest |& tee x || true", "pytest &> log || true", "pytest -q; true",
                "pytest; :", "(pytest -q) || true", "{ pytest -q; true; }", "pytest -q || exit 0", "pytest -q || (true)",
                "pytest || /bin/true", "cd app && npm test || true", "npm run build && npm test || true",
                "pytest && echo ok || true", "pytest; echo done; exit 0", "bash -c 'pytest || true'", "sh -c \"npm test || true\"",
                "bash -c 'pytest' || true", "ruff check --exit-zero", "pylint x --exit-zero", "eslint . --exit-zero",
                "pytest --exit-zero", "timeout 60 pytest || true", "env CI=1 pytest || true", "time pytest || true",
                "nohup pytest || true", "echo 'pytest || true' | sh", "pytest -q 2>&1 | tail -5 || true", "pytest tests/ -x -q || true\n"):
        deny(cmd, E)
    for cmd in ("cat tsconfig.json || true", "grep -rn jest package.json || true", "ls .ruff_cache || true",
                "rm -rf .mypy_cache .pytest_cache || true", "pytest -q", "npm test", "pytest -q 2>&1 | tail -20",
                "pytest -q | tee out.log", "npm run build && npm test", "npm run build || true", "npm install || true",
                "git status || true", "make build || true", "make || true", "make clean || true", "rm -rf dist || true; npm test",
                "npm test; echo done", "pytest -q; echo \"exit $?\"", "pytest -q && true", "pytest -q || echo failed",
                "pytest -q || exit 1", "ls || true", "echo pytest || true", "git commit -m 'pytest || true'",
                "grep -rn -- '--exit-zero' .", "echo --exit-zero", "true", "test -f x || true", "[ -f x ] || true",
                "which pytest || true", "command -v pytest || true", "type pytest || true", "pip install pytest || true",
                "npx --yes create-thing || true", "python -m pip install x || true", "python script.py || true",
                "pnpm install || true", "npm run dev || true", "yarn install || true", "yarn build || true", "cargo build || true",
                "go build || true", "go vet ./... || true", "make -C tests build || true",
                "cat > ci.sh <<'EOF'\npytest || true\nEOF", "echo 'pytest || true' >> ci.sh", "git log --grep='|| true'",
                "npm test 2>&1 | tail -5", "pytest -q --maxfail=1", "cd app; npm test"):
        allow(cmd, "feat", "secrets")


def snapshot_rules(allow, deny, adjacent):
    S = "re-record snapshots"
    for cmd in ("jest --updateSnapshot", "jest --updateSnapshot --ci=false", "vitest run -u", "vitest --update", "npm run test -- -u",
                "yarn test -u", "pnpm test -u", "playwright test -u", "pytest --snapshot-update", "npx jest --updateSnapshot=all",
                "bash -c 'jest -u'", "./scripts/regen.sh --update-snapshots", "cd app && npx jest -u", "npm test -- --updateSnapshot"):
        deny(cmd, S)
    for cmd in ("jest", "jest --ci", "vitest run", "mocha -u tdd", "npm install -u", "npm run build -- -u", "yarn upgrade -u",
                "git commit -m 'jest -u'", "grep -rn 'updateSnapshot' src", "echo jest -u", "pnpm up -u", "pip install -U x",
                "git log --grep=--update-snapshots", "echo '--update-snapshots'"):
        allow(cmd, "feat", "secrets")


def secret_rules(allow, deny, adjacent):
    K = "secret file"
    for cmd in ("cat .env.local", "cat .env.production", "head -3 .env", "tail -f .env", "less .env", "grep KEY .env",
                "grep -n KEY .env.local", "rg TOKEN .env", "sed -n 1p .env", "awk '{print}' .env", "cut -d= -f2 .env", "cat app/.env",
                "cat ./.env", "cp .env /tmp/x", "cat \"$HOME/.aws/credentials\"", "cat $HOME/.ssh/id_rsa", "head ~/.ssh/id_ed25519",
                "cat ~/.ssh/id_ecdsa", "cat ~/.netrc", "cat ~/.pypirc", "base64 ~/.ssh/id_rsa", "cat " + OTHER_MAC_HOME + "/.aws/credentials",
                "cat " + OTHER_LINUX_HOME + "/.ssh/id_rsa", "cat /root/.netrc", "xxd .env", "strings .env", "wc -l < .env",
                "while read l; do echo $l; done < .env", "cat < ~/.netrc", "echo $(cat .env)", "bash -c 'cat .env'", "cat .env | grep X",
                "diff .env .env.example", "jq . ~/.config/gh/hosts.yml", "cat ${HOME}/.npmrc", "tac .env", "nl .env", "cat -n .env",
                "grep -e KEY .env", "cd app && cat .env", "cat ~/.ssh/id_rsa > /tmp/k"):
        deny(cmd, K, "secrets")
        allow(cmd, "feat")
    for cmd in ("cat .env.example", "cat .env.sample", "cat .env.template", "cat ~/.ssh/id_rsa.pub", "ls -la .env", "ls ~/.aws/",
                "test -f .env", "[ -f .env ]", "touch .env", "echo FOO=1 >> .env", "echo FOO=1 > .env", "cp .env.example .env",
                "git add .env.example", "git check-ignore .env", "printenv | grep -i key", "env | sort", "printenv HOME",
                "grep -rn '.env' src/", "grep -rn 'process.env' src", "find . -name .env", "cat README.md", "cat envfile", "cat .envrc",
                "cat myenv", "cat foo.env", "ssh-add ~/.ssh/id_rsa", "ssh -i ~/.ssh/id_rsa host", "source .env", ". .env",
                "docker compose --env-file .env up", "chmod 600 ~/.ssh/id_rsa", "cat ~/.aws/config", "cat ~/.ssh/config",
                "cat ~/.ssh/known_hosts", "cat ~/.gitconfig", "git commit -m 'cat .env'", "echo 'cat .env'", "cat .npmrc",
                "cat project/.netrc", "head -c 100 ~/.ssh/id_rsa.pub", "rg 'API_KEY' src", "sed -i 's/a/b/' package.json",
                "awk '{print}' notes.txt", "cat notes.txt | grep .env"):
        allow(cmd, "feat", "secrets")
    allow("cat .env.staging", "feat", "secrets-custom")
    allow("grep DATABASE_URL .env.staging", "secrets-custom")
    deny("cat .env.production", K, "secrets-custom")
    deny("cat .env.staging", K, "secrets")


def trailer_rules(allow, deny, adjacent):
    F = "forbidden"
    T = "trail"
    deny("git commit -m 'x' -m 'co-authored-by: a <a@b>'", F, T)
    deny("git commit --message='x\n\nCo-Authored-By: a'", F, T)
    deny("git commit -am 'x\n\nCo-Authored-By: a <a@b>'", F, T)
    deny("git commit -m \"$(cat <<'EOF'\nfix\n\nCo-Authored-By: Claude <noreply@anthropic.com>\nEOF\n)\"", F, T)
    deny("git commit -F - <<< $'x\\n\\nCo-Authored-By: a <a@b>'", F, T)
    deny("printf 'x\\n\\nCo-Authored-By: a <a@b>\\n' | git commit -F -", F, T)
    deny("git commit -m $'x\\n\\nCo-Authored-By: a <a@b>'", F, T)
    deny("git commit --trailer 'Co-Authored-By: a' -m x", F, T)
    deny("git commit --trailer='Co-authored-by: a <a@b>' -m x", F, T)
    deny("git commit -m x --trailer \"Co-Authored-By=a <a@b>\"", F, T)
    deny("git -C . commit -m 'x\n\nCo-Authored-By: a <a@b>'", F, T)
    deny("bash -c \"git commit -m 'x' -m 'Co-Authored-By: a <a@b>'\"", F, T)
    deny("cat > /tmp/deny-m.txt <<'EOF'\nfix\n\nCo-Authored-By: a <a@b>\nEOF\ngit commit -F /tmp/deny-m.txt", F, T)
    deny("echo 'Co-Authored-By: a <a@b>' > m.txt && git commit -F m.txt", F, T)
    deny("git commit-tree HEAD^{tree} -F msg.txt", F, T)
    deny("git commit --amend --trailer 'Co-Authored-By: a <a@b>'", F, T)
    deny("git commit -m x -m 'Co-Authored-By: a <a@b>'", F, "attr")
    deny("git commit -m x -m 'Co-Authored-By: a <a@b>'", F, "badjson")
    deny("git commit -m x -m 'Signed-off-by: a <a@b>'", F, "custom")
    allow("git commit -m x -m 'Co-Authored-By: a <a@b>'", "custom", "attr-off", "plain", "feat")
    allow("git commit -F msg.txt", "attr-off", "plain")
    allow("git commit-tree HEAD^{tree} -m 'x\n\nCo-Authored-By: a <a@b>'", "plain", "feat")
    allow("git commit -m 'x' -m 'body mentions Co-Authored-By: inline'", "trail")
    allow("git commit -m fix && git log --format=%B | grep -i 'co-authored-by:'", "trail")
    allow("git commit -m 'Signed-off-by: a <a@b>'", "trail")
    allow("git commit --amend --no-edit", "trail")
    allow("git commit -m x", "trail")
    allow("git commit -F clean.txt", "trail")
    allow("git commit -F nonexistent.txt", "trail")
    allow("git commit -F - <<'EOF'\nfix\nEOF", "trail")
    allow("echo 'x' | git commit -F -", "trail")
    allow("echo 'Co-Authored-By: x' >> NOTES.md; git commit -m 'notes'", "trail")
    allow("git log --grep='Co-Authored-By:'", "trail")
    allow("git commit -m 'fix: mention Co-Authored-By: in docs'", "trail", "attr")


def parser_shapes(allow, deny, adjacent):
    for cmd in ("ls", "ls -la && pwd", "echo hello", "cat README.md | head", "git status", "git diff --stat",
                "git add -A && git commit -m 'x'", "npm run build", "cd sub && ls", "for f in *.txt; do echo $f; done",
                "while read l; do echo \"$l\"; done < list.txt", "x=$(date); echo $x", "echo $((1+2))", "[[ -f x ]] && echo y",
                "case $x in a) echo 1;; esac", "f() { echo hi; }; f", "echo 'unterminated", "echo \"unterminated", "echo `", "`",
                "))", "((", "{", "}", ";;", "|", "&&", ">", "<", "$(", "<<", "cat <<EOF", "cat <<EOF\nno end", "$(((", "${", "${x", "\\",
                "a\\", "echo ${HOME:-/tmp}/x", "echo ${#PATH}", "echo $#", "echo $@", "echo a#b", "FOO=bar", "> file", "2>&1",
                "cmd 2>&1 | tee log", "echo $'\\x41'", "ls <(echo a)", "diff <(ls a) <(ls b)", "true || false", "! false",
                "(", ")", "( )", "echo (a)", "if x; then y", "done", "fi", "echo ok &", "echo a;b", "echo $(echo $(echo a))",
                "echo \"a $(echo \"b\") c\"", "echo '\"'", "echo \"'\"", "git commit -m \"it's fine\"", "printf '%s\\n' \"$x\""):
        allow(cmd, "feat", "secrets")


def context_rules(allow, deny, adjacent):
    deny("cd sub && git push", PROT, "main")
    allow("cd ../feat && git push", "main")
    deny("cd ../main && git push", PROT, "feat")
    deny("git -C ../main push", PROT, "feat")
    allow("git -C ../feat push", "main")
    deny("(cd ../main && git push)", PROT, "feat")
    allow("(cd ../feat && git push); git status", "main")
    deny("cd ../main; git push origin HEAD", PROT, "feat")
    allow("cd ../main && cd ../feat && git push", "main")
    deny("(cd ../feat); git push", PROT, "main")
    deny("cd ../feat && rm -rf *", "recursive delete", "main")
    allow("cd .. && rm -rf *", "main")
    allow("cd sub && rm -rf *", "main")
    deny("rm -rf *", "recursive delete", "main")
    deny("echo a | xargs sh -c 'git push origin main'", PROT)
    deny("echo a | xargs -I{} bash -c 'rm -rf /'", "recursive delete")
    deny("find . -name x | xargs -n1 sh -c 'sudo x'", "sudo")
    deny("echo " + "{a,b}" * 14, "deny hook error")
    deny("B=main; git push origin $B", PROT)
    deny("B=main && git push origin \"$B\"", PROT)
    deny("export B=main; git push origin ${B}", PROT)
    deny("B=$(git branch --show-current); git push origin \"$B\"", PROT, "main")
    allow("B=$(git branch --show-current); git push origin \"$B\"", "feat")
    deny("git push origin $(git branch --show-current)", PROT, "main")
    allow("git push origin $(git branch --show-current)", "feat")
    deny("git push origin \"$(git rev-parse --abbrev-ref HEAD)\"", PROT, "main")
    allow("B=feature/x; git push origin $B")
    allow("(B=main); git push origin $B")
    adjacent("git push origin $UNKNOWN_BRANCH")
    deny("git checkout main && git pull && git push", PROT, "feat")
    deny("git switch main && git push origin HEAD", PROT, "feat")
    allow("git checkout -b feature/new && git push -u origin HEAD", "main")
    allow("git checkout feature/x && git push", "main")
    deny("git checkout -- file && git push", PROT, "main")
    deny("git checkout README.md && git push", PROT, "main")
    allow("(git checkout main); git push", "feat")
    deny("git checkout main; git checkout feature/x; git checkout main; git push", PROT, "feat")
    deny("D=/; rm -rf $D", "recursive delete")
    allow("D=build; rm -rf \"$D\"")
    deny("N=99; gh pr merge $N", PROT)
    allow("N=12; gh pr merge $N")
    deny("bash -c \"$(cat <<'EOF'\ngit push origin main\nEOF\n)\"", PROT)
    deny("eval \"$(echo 'rm -rf /')\"", "recursive delete")
    deny("bash -c \"$(printf 'sudo ls')\"", "sudo")
    allow("eval \"$(ssh-agent -s)\"")
    allow("bash -c \"$(cat <<'EOF'\necho hi\nEOF\n)\"")


def everyday(allow, deny, adjacent):
    body = "## Summary\n- never git push origin main\n- rm -rf / is bad, sudo too\n\nUses `ticks`, $vars and $(subst) as text.\n"
    allow("gh pr create --title \"feat: x\" --body \"$(cat <<'EOF'\n" + body + "EOF\n)\"")
    allow("git commit -m \"$(cat <<'EOF'\nfeat: it's fine\n\nBody with \"quotes\", $vars and `ticks` and sudo.\nEOF\n)\"", "feat", "trail")
    for cmd in ("git diff main...HEAD", "git log main..feature/t --oneline", "git checkout main", "git merge origin/main",
                "git rebase origin/main", "git fetch --all --prune", "git branch -d old", "git worktree add ../wt -b feature/x main",
                "git stash pop", "git tag v1.0 && git push origin v1.0", "npm run lint && npm run test", "npx prettier --check .",
                "docker compose logs --tail=50 | grep -i error || true", "curl -s localhost:3000/health || true",
                "lsof -ti:3000 | xargs kill -9 2>/dev/null || true", "kill $(lsof -ti:3000) || true", "pkill -f uvicorn || true",
                "sleep 5 && curl -sf http://localhost:8000/health", "python -m http.server 8000 &", "nohup npm run dev > dev.log 2>&1 &",
                "tail -f log | grep --line-buffered x", "find . -name '*.pyc' -delete", "find . -type f -name '*.log' -exec rm {} +",
                "rm -rf .next && npm run build", "rm -rf node_modules && npm ci", "rm -rf $TMPDIR/foo",
                "make test-unit || true", "cat package.json | jq .scripts", "echo \"$OUTPUT\" | grep -q ok",
                "psql \"$DATABASE_URL\" -c \"\\dt\"", "env | grep FOO", "source venv/bin/activate && pytest -q",
                "cd frontend && npm test -- --watchAll=false", "npx jest --ci --coverage",
                "git add -A && git commit -m 'x' && git push origin HEAD", "gh pr checks", "gh run watch",
                "gh api repos/o/r/pulls/12/comments", "openssl rand -hex 32 > .env.local", "echo \"KEY=$(openssl rand -hex 32)\" >> .env",
                "cp .env.example .env.local", "mv .env.local .env.old", "git show HEAD:README.md", "sed -n '1,20p' file.py",
                "sed -i '' 's/a/b/' file.py", "rsync -a src/ dest/", "tar czf x.tgz src", "uvicorn app:app --reload &",
                "python manage.py migrate", "alembic upgrade head", "npx prisma migrate dev", "supabase start",
                "ls -la | head -20", "wc -l $(git ls-files)", "diff <(git show a:f) <(git show b:f)", "xargs -0 -n1 echo < list",
                "awk -F, '{print $1}' data.csv | sort | uniq -c", "for i in 1 2 3; do curl -s localhost:$i || true; done",
                "if [ -f x ]; then echo yes; else echo no; fi", "trap 'rm -f /tmp/x' EXIT", "set -euo pipefail",
                "export FOO=bar && npm start", "FOO=bar BAZ=qux node app.js", "echo done; exit 0", "true; exit 0", "exit 1",
                "git status --short | wc -l", "git log --oneline -5 --format='%h %s'", "sqlite3 app.db '.tables'",
                "sqlite3 app.db 'select count(*) from t'", "mysql -e 'show tables'", "chmod 600 ~/.ssh/id_rsa", "chmod -R 755 dist"):
        allow(cmd, "feat", "secrets")


def build(allow, deny, adjacent):
    for group in (push_rules, merge_rules, rm_rules, git_rules, sql_rules, privilege_rules, suppression_rules, snapshot_rules,
                  secret_rules, trailer_rules, parser_shapes, context_rules, everyday):
        group(allow, deny, adjacent)
