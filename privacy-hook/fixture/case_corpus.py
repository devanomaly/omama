#!/usr/bin/env python3
"""Table-driven corpus for the privacy-hook, run through real git commits.

Every case gets its OWN throwaway repo (built by lib.make_repo, which
installs the shipped `pre-commit` + `scan_staged.py` byte-for-byte), is
staged the way the case defines, and then really commits. The polarity
asserted is the exit code of `git commit` itself -- not a call into the
scanner's internals -- so a case can only go green if the artifact a
colleague installs behaves that way.

THIS CORPUS IS THE PROOF OF A NARROW CLAIM. The generic "<secret-ish key>
= <high-entropy value>" rule was REMOVED from this piece (see
scan_staged.py's module docstring and the README). The corpus therefore
has three load-bearing halves, not two:

  * BLOCK -- one red case per KEPT pattern (AWS key id, GitHub classic +
    fine-grained, PEM, PuTTY, Anthropic, Slack, URL credentials), plus the
    two deterministic layers this piece is actually best at
    (deny_filenames, the literal token list) and the deny_regexes layer,
    plus the fail-closed config diagnostics. If any of these regresses,
    the corpus goes red here.

  * PASS / false-positive corpus -- the SIXTEEN measured false positives
    from the wave-A2 re-attack, verbatim, each in its own case. These are
    the reason the scope was cut. If any of them starts blocking again,
    the corpus goes red here. Five of the sixteen were `url-credentials`
    hits and one was the AWS documentation example key; those six are
    green because of the explicit allowlist in scan_staged.py, and each
    one is that allowlist's red-green proof.

  * PASS / no-regeneration tripwire -- payloads that ARE secrets and now
    commit clean, on purpose, because the rule that caught them is gone.
    They are asserted as PASS so that anyone who re-adds a broad value
    rule (or a "weaker version of itself") sees the corpus go red HERE
    first, and has to argue with the measurement instead of quietly
    reintroducing the 1:1 error trade. Each carries the receipt it came
    from.

Cases carry optional assertions beyond polarity:
  * `forbidden` -- a string the hook's own output must never echo (the
    matched secret, an absolute path, a traceback marker).
  * `expect_output` -- a substring the output MUST contain, used where
    the promise is about the DIAGNOSTIC and not only the verdict.

Exit 0 only if every case behaved as declared; 1 otherwise, naming each
offender. Repos of passing cases are deleted; repos of failing cases are
kept and their path printed, for post-mortem.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

BLOCK = "block"
PASS = "pass"


# --- staging helpers ----------------------------------------------------
def stage_content(relpath, content):
    """Write `content` at `relpath` and stage it. Nothing else."""
    def stage(repo):
        lib.write_file(repo, relpath, content)
        r = lib.git(repo, "add", relpath)
        if r.returncode != 0:
            return "git add failed: %s" % r.stderr.strip()
        return None
    return stage


def stage_rename(src, dst, content=b"debug = true\n", no_verify=False):
    """Commit `src` first, then `git mv src dst` and leave the rename
    staged.

    `no_verify` models the repo state this hook has to survive in real
    life: a file whose content was NEVER vetted (committed with
    `--no-verify`, or committed before the deny-list grew) already sits in
    history. A later pure rename of that file is the moment the hook gets
    its first look at it -- which it only gets if renames are in the
    diff-filter."""
    def stage(repo):
        lib.write_file(repo, src, content)
        r = lib.git(repo, "add", src)
        if r.returncode != 0:
            return "git add %s failed: %s" % (src, r.stderr.strip())
        base = ["commit", "-m", "base: add %s" % src]
        if no_verify:
            base.append("--no-verify")
        r = lib.git(repo, *base)
        if r.returncode != 0:
            return ("baseline commit of %s failed -- the rename case cannot "
                    "be trusted: %s %s"
                    % (src, r.stdout.strip(), r.stderr.strip()))
        dst_dir = os.path.dirname(os.path.join(repo, dst))
        if dst_dir:
            os.makedirs(dst_dir, exist_ok=True)
        r = lib.git(repo, "mv", src, dst)
        if r.returncode != 0:
            return "git mv %s %s failed: %s" % (src, dst, r.stderr.strip())
        return None
    return stage


def stage_remove_config(name):
    """Stage the deletion of a config file the hook depends on, plus an
    innocent file, to assert the fail-closed behaviour is still in force."""
    def stage(repo):
        r = lib.git(repo, "rm", "-q", name)
        if r.returncode != 0:
            return "git rm %s failed: %s" % (name, r.stderr.strip())
        lib.write_file(repo, "src/ok.py", b"x = 1\n")
        lib.git(repo, "add", "src/ok.py")
        return None
    return stage


def stage_broken_config(raw):
    """Leave a malformed deny-list config in the WORKING TREE (that is
    where the hook reads it from) and stage an innocent file."""
    def stage(repo):
        lib.write_file(repo, "privacy-deny.json", raw)
        lib.write_file(repo, "src/ok.py", b"x = 1\n")
        lib.git(repo, "add", "src/ok.py")
        return None
    return stage


def stage_secret_in_config(payload):
    """Put a secret inside privacy-deny.json itself -- the one file the
    README tells every adopting team to commit."""
    def stage(repo):
        path = os.path.join(repo, "privacy-deny.json")
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["_note"] = payload
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        r = lib.git(repo, "add", "privacy-deny.json")
        if r.returncode != 0:
            return "git add failed: %s" % r.stderr.strip()
        return None
    return stage


def stage_case_variant_config(name, content):
    """Write a blob straight into the index under `name` -- a case variant
    of the config file name. `git update-index --cacheinfo` is used
    because a case-insensitive filesystem cannot hold both names at once,
    while a case-sensitive checkout (Linux/CI) resolves them as two
    different, real files."""
    def stage(repo):
        scratch = os.path.join(repo, ".payload-tmp")
        with open(scratch, "wb") as f:
            f.write(content)
        r = lib.git(repo, "hash-object", "-w", ".payload-tmp")
        if r.returncode != 0:
            return "hash-object failed: %s" % r.stderr.strip()
        sha = r.stdout.strip()
        os.remove(scratch)
        r = lib.git(repo, "update-index", "--add", "--cacheinfo",
                    "100644,%s,%s" % (sha, name))
        if r.returncode != 0:
            return "update-index failed: %s" % r.stderr.strip()
        return None
    return stage


def stage_tokens_file_redirect(target, content):
    """Point `tokens_file` at an ordinary application file. The config is
    trusted enough to define the deny-list, but it must not be able to
    turn an arbitrary path into a scan-free channel."""
    def stage(repo):
        path = os.path.join(repo, "privacy-deny.json")
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["tokens_file"] = target
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        lib.write_file(repo, target, content)
        r = lib.git(repo, "add", target, "privacy-deny.json")
        if r.returncode != 0:
            return "git add failed: %s" % r.stderr.strip()
        return None
    return stage


def stage_submodule(path):
    """Stage a submodule pointer (a gitlink, index mode 160000). It has no
    blob at all, so `git show :<path>` fails -- which used to make the
    hook block every submodule-bumping commit in every repo that uses
    submodules."""
    def stage(repo):
        inner = os.path.join(repo, path)
        os.makedirs(inner, exist_ok=True)
        for args in (("init", "-q"),
                     ("config", "user.email", "fixture@example.test"),
                     ("config", "user.name", "Fixture Runner")):
            r = lib.git(inner, *args)
            if r.returncode != 0:
                return "inner git %s failed: %s" % (args[0], r.stderr.strip())
        with open(os.path.join(inner, "a.txt"), "wb") as f:
            f.write(b"inner\n")
        lib.git(inner, "add", "a.txt")
        r = lib.git(inner, "commit", "-q", "-m", "inner")
        if r.returncode != 0:
            return "inner commit failed: %s %s" % (r.stdout.strip(),
                                                   r.stderr.strip())
        r = lib.git(repo, "add", path)
        if r.returncode != 0:
            return "git add %s failed: %s" % (path, r.stderr.strip())
        return None
    return stage


# --- payloads -----------------------------------------------------------
# Shape-valid, never live. A synthetic AKIA-prefixed key is used instead of
# AWS's own published example key everywhere a BLOCK is expected -- the
# published one is reserved for the allowlist cases (see the two
# `neg-fp-aws-doc-example-key-in-test` / `allowlist-aws-doc-key-one-char-off`
# cases). Every credential shape on this page is assembled by concatenation
# below (never written as one contiguous literal): this fixture's own
# source has to pass privacy-hook's built-in scanner too, so an adopting
# repo -- including this one -- can commit a fixture edit through the hook
# (see fixture-source-self-clean in check.py). The BYTES a case plants at
# runtime are unchanged; only how the literal is spelled in the source is
# different.
AWS_KEY_BLOCKING = b"AKIA" + b"ABCDEFGHIJKLMNOP"

# STS/assumed-role prefix, split for the same reason as AWS_KEY_BLOCKING.
AWS_STS_KEY_BLOCKING = b"ASIA" + b"IOSFODNN7EXAMPLE"

# One character off the allowlisted AWS documentation key -- split so the
# near-miss literal doesn't itself match the shape it's built to trigger.
AWS_DOC_KEY_ONE_CHAR_OFF = b"AKIAIOSFODNN7EXAMPL" + b"Z"

# GitHub classic token shape (ghp_ + 36 chars), split for the same reason.
GITHUB_TOKEN_BLOCKING = b"ghp_" + b"A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"

# PuTTY private-key header, split for the same reason.
PUTTY_HEADER_BLOCKING = b"PuTTY-User-Key-File-" + b"3"

# Anthropic key shape, split for the same reason.
ANTHROPIC_KEY_BLOCKING = b"sk-ant-" + b"api03-AbCdEfGhIjKlMnOpQrSt"

# Slack token shape, split for the same reason.
SLACK_TOKEN_BLOCKING = b"xoxb-" + b"1234567890-0987654321-AbCdEfGhIjKl"

PEM_BLOCK = (
    # only the BEGIN line matches the built-in private-key-block shape, so
    # only it needs splitting.
    b"-----BEGIN RSA PRIVATE" + b" KEY-----\n"
    b"MIIEogIBAAKCAQEAxLotsyk3Ff0XoLotsyk3Ff0XoLotsyk3Ff0XoLotsyk3Ff0X\n"
    b"-----END RSA PRIVATE KEY-----\n"
)

UTF16_AWS = ('KEY = "' + AWS_KEY_BLOCKING.decode() + '"\n').encode("utf-16-le")
UTF16_BOM_TOKEN = 'tok = "EXAMPLE-DENY-TOKEN"\n'.encode("utf-16")

# --- the sixteen measured false positives, verbatim ---------------------
# Source: toolkit-staging/attack-findings-wave-a2.json ->
# reattack_01.false_positives. Every byte below is transcribed from that
# receipt, not paraphrased.
FP_COMPOSE_POSTGRES_URL = (
    b"services:\n"
    b"  api:\n"
    b"    image: app:dev\n"
    b"    environment:\n"
    b"      DATABASE_URL: postgres://postgres:postgres@db:5432/appdb\n"
)
FP_README_QUICKSTART = (
    b"## Quickstart\n"
    b"\n"
    b"```sh\n"
    b"export DATABASE_URL=postgres://postgres:postgres@localhost:5432/appdb\n"
    b"export REDIS_URL=redis://:devpass@localhost:6379/0\n"
    b"```\n"
)
FP_COMPOSE_RABBITMQ = (
    b"services:\n"
    b"  worker:\n"
    b"    environment:\n"
    b"      BROKER_URL: amqp://guest:guest@rabbitmq:5672//\n"
)
FP_DOCS_MONGO = b"Connect with `mongodb://root:example@localhost:27017/`.\n"
FP_DOCS_CURL = (
    b"Healthcheck:\n"
    b"\n"
    b"    curl https://admin:admin@localhost:8080/health\n"
)
FP_ENV_EXAMPLE_SERVICES = (
    b"# copie para .env e preencha\n"
    b"STRIPE_SECRET_KEY=your_stripe_secret_key\n"
    b"REDIS_PASSWORD=your_redis_password\n"
    b"SUPABASE_API_KEY=your-supabase-anon-key\n"
    b"JWT_SECRET=troque_por_um_valor_aleatorio\n"
)
FP_COMPOSE_LOCALDEV_PASSWORD = (
    b"services:\n"
    b"  db:\n"
    b"    image: postgres:16\n"
    b"    environment:\n"
    b"      POSTGRES_PASSWORD: localdevpassword\n"
)
FP_JS_PASSWORD_PROPERTY = (
    b"export function login(form) {\n"
    b"  const body = { email: form.email, password: form.passwordConfirmation };\n"
    b"  return http.post('/login', body);\n"
    b"}\n"
)
FP_TS_PASSWORD_PROPERTY = (
    b"export async function signIn(r: Creds) {\n"
    b"  http.post('/login', { email: r.email, password: r.plaintextPassword });\n"
    b"}\n"
)
FP_PY_PASSWORD_DICT = (
    b"def build(hashed_password_from_form):\n"
    b'    payload = {"password": hashed_password_from_form}\n'
    b"    return payload\n"
)
FP_TEST_FAMOUS_PASSWORD = (
    b'TEST_USER = {"username": "alice", "password": "correcthorsebatterystaple"}\n'
)
FP_TERRAFORM_RANDOM_PASSWORD = (
    b'resource "aws_db_instance" "main" {\n'
    b"  username   = \"app\"\n"
    b"  password   = random_password.db_master.result\n"
    b"}\n"
)
FP_HELM_BITNAMI_DEFAULT = (
    b"global:\n"
    b"  postgresql:\n"
    b"    auth:\n"
    b"      password: releaseNamePostgresql\n"
)
FP_DOCS_PTBR_DEV_LOCAL = (
    b"# Variaveis de ambiente\n"
    b"\n"
    b"Valor padrao em dev: `POSTGRES_PASSWORD=postgres_dev_local`\n"
)
FP_AWS_DOC_KEY_IN_TEST = (
    b"import os\n"
    b'os.environ["AWS_ACCESS_KEY_ID"] = "AKIAIOSFODNN7EXAMPLE"\n'
    b'os.environ["AWS_SECRET_ACCESS_KEY"] = "wJalrXUtnFEMI/K7MDENG/'
    b'bPxRfiCYEXAMPLEKEY"\n'
)
FP_DJANGO_INSECURE_SECRET_KEY = (
    b"SECRET_KEY = 'django-insecure-8k2#hq3v!x9zm4wp1rt6yu0oa5ceg7bn'\n"
)

# --- tripwire payloads: capability deliberately removed -----------------
TRIPWIRE_ENV_EXAMPLE = (
    b"# copie para .env e preencha\n"
    b"SECRET_KEY=your-secret-key-here\n"
    b"API_KEY=your-api-key-goes-here\n"
    b"DATABASE_PASSWORD=REPLACE_WITH_REAL_PASSWORD\n"
)
TRIPWIRE_DJANGO_SETTINGS = (
    b'PASSWORD_HASHERS = [\n'
    b'    "django.contrib.auth.hashers.Argon2PasswordHasher",\n'
    b']\n'
    b'PASSWORD_RESET_TIMEOUT = 3600\n'
    b'SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]\n'
)


# --- the corpus --------------------------------------------------------
# Fields: (case id, expected polarity, staging fn, forbidden-in-output,
#          required-in-output)
def C(case_id, expect, stage, forbidden=None, expect_output=None):
    return (case_id, expect, stage, forbidden, expect_output)


CASES = [
    # =================================================================
    # BLOCK -- one red case per KEPT built-in pattern. These are the
    # structural, vendor-documented shapes that survived the scope cut.
    # =================================================================
    C("builtin-aws-access-key-id", BLOCK,
      stage_content("config/aws.env", b"AWS_ACCESS_KEY_ID=" + AWS_KEY_BLOCKING + b"\n"),
      AWS_KEY_BLOCKING.decode()),
    # ASIA = STS/assumed-role prefix. Uses the doc key's SUFFIX with the
    # ASIA prefix, so it also proves the allowlist is not prefix-fuzzy.
    C("builtin-aws-sts-key", BLOCK,
      stage_content("sts.env",
                    b"AWS_ACCESS_KEY_ID=" + AWS_STS_KEY_BLOCKING + b"\n"), None),
    # One character off the allowlisted AWS documentation key. The
    # allowlist is a byte-exact literal set, not a prefix or a pattern.
    C("allowlist-aws-doc-key-one-char-off", BLOCK,
      stage_content("app/boot.py",
                    b'KEY = "' + AWS_DOC_KEY_ONE_CHAR_OFF + b'"\n'), None),
    C("builtin-github-classic-token", BLOCK,
      stage_content("ci.env",
                    b"GH_TOKEN=" + GITHUB_TOKEN_BLOCKING + b"\n"), None),
    C("builtin-github-fine-grained-pat", BLOCK,
      stage_content("ci.env",
                    b"GH_TOKEN=github_pat_11ABCDEFG0abcdefghij_"
                    b"KLMNOPQRSTUVWXYZ0123456789abcdefghijKLMNOPQ\n"), None),
    C("builtin-pem-private-key", BLOCK,
      stage_content("deploy/server_key", PEM_BLOCK), None),
    C("builtin-putty-private-key", BLOCK,
      stage_content("server.ppk",
                    PUTTY_HEADER_BLOCKING + b": ssh-rsa\nEncryption: none\n"), None),
    C("builtin-anthropic-key", BLOCK,
      stage_content("svc.env",
                    b"ANTHROPIC_API_KEY=" + ANTHROPIC_KEY_BLOCKING + b"\n"), None),
    C("builtin-slack-token", BLOCK,
      stage_content("svc.env",
                    b"SLACK_BOT_TOKEN=" + SLACK_TOKEN_BLOCKING + b"\n"),
      None),
    C("builtin-url-credentials-upper-scheme", BLOCK,
      # split before the at-sign so this line doesn't itself carry a
      # complete credentials-in-a-URL match
      stage_content("conn.txt",
                    b"POSTGRES://admin:s3cr3t" + b"pw@db.example.com/app\n"),
      "s3cr3tpw"),
    C("builtin-url-credentials-slash-in-pass", BLOCK,
      stage_content("conn2.txt",
                    b"mongodb://admin:pa/s" + b"s@db.example.com/app\n"),
      None),
    # The allowlist is a PAIR, not a username: change the password half and
    # the same URL blocks again.
    C("allowlist-url-pair-one-side-changed", BLOCK,
      stage_content("docker-compose.yml",
                    b"      DATABASE_URL: postgres://postgres:"
                    b"hunter2hunter2@db:5432/appdb\n"), None),
    # One allowlisted occurrence must not shield a real credential in the
    # SAME file -- builtin_hit() iterates every match, not just the first.
    C("allowlist-mixed-allowlisted-and-real", BLOCK,
      stage_content("docker-compose.yml",
                    b"      DATABASE_URL: postgres://postgres:postgres@db:5432/appdb\n"
                    b"      LEGACY_URL: mysql://admin:s3cr3t" + b"pw@legacy.example.com/db\n"),
      "s3cr3tpw"),

    # =================================================================
    # BLOCK -- the two deterministic layers this piece is best at, plus
    # the team regex layer. No off-the-shelf scanner knows a client
    # codename, an internal hostname or a project alias.
    # =================================================================
    C("deny-filename-added", BLOCK, stage_content(".env", b"debug = true\n"), None),
    # A DIRECTORY named `.env`. No basename regex can express this shape,
    # so deny_filenames is matched against every path component.
    C("deny-filename-directory", BLOCK,
      stage_content(".env/local", b"SUPER=SECRET\n"), None),
    C("deny-filename-via-rename", BLOCK, stage_rename("settings.txt", ".env"), None),
    C("deny-token-literal", BLOCK,
      stage_content("notes/internal.md",
                    b"reference: EXAMPLE-DENY-TOKEN in the ticket\n"),
      "EXAMPLE-DENY-TOKEN"),
    C("deny-regex-internal-hostname", BLOCK,
      stage_content("docs/runbook.md",
                    b"ssh deploy@internal.example.corp\n"),
      "internal.example.corp"),

    # =================================================================
    # BLOCK -- reach: renames, wide encodings, the config itself.
    # =================================================================
    C("secret-content-via-rename", BLOCK,
      stage_rename("legacy.txt", "archive/notes.txt",
                   content=b"AWS_ACCESS_KEY_ID=" + AWS_KEY_BLOCKING + b"\n",
                   no_verify=True),
      AWS_KEY_BLOCKING.decode()),
    C("utf16le-builtin-pattern", BLOCK, stage_content("keys.txt", UTF16_AWS), None),
    C("utf16-bom-deny-token", BLOCK, stage_content("notes.txt", UTF16_BOM_TOKEN),
      None),
    C("secret-inside-deny-config", BLOCK,
      stage_secret_in_config(AWS_KEY_BLOCKING.decode()), None),
    C("case-variant-config-name", BLOCK,
      stage_case_variant_config("PRIVACY-DENY.JSON",
                                AWS_KEY_BLOCKING + b"\n"), None),
    C("tokens-file-redirect", BLOCK,
      stage_tokens_file_redirect("app/creds.txt",
                                 AWS_KEY_BLOCKING + b"\n" + PEM_BLOCK), None),

    # ---- BLOCK: fail-closed config paths. These assert the DIAGNOSTIC,
    # not only the verdict.
    C("fail-closed-missing-config", BLOCK,
      stage_remove_config("privacy-deny.json"), None, "missing-config"),
    C("fail-closed-missing-tokens-file", BLOCK,
      stage_remove_config("privacy-tokens.txt"), None, "missing-tokens-file"),
    C("fail-closed-malformed-config", BLOCK,
      stage_broken_config(b"{ not json \n"), "Traceback", "bad-config"),
    C("fail-closed-bad-regex-config", BLOCK,
      stage_broken_config(b'{"deny_regexes": [{"id": "x", "pattern": "([unclosed"}]}\n'),
      "Traceback", "bad-config"),

    # =================================================================
    # PASS -- THE FALSE-POSITIVE CORPUS. All sixteen measured false
    # positives from attack-findings-wave-a2.json, verbatim. Each one is
    # ordinary repo content; each one blocked before the scope cut.
    # The first six are green because of the explicit allowlist; the rest
    # are green because the generic assignment rule is gone.
    # =================================================================
    C("neg-fp-compose-postgres-url", PASS,
      stage_content("docker-compose.yml", FP_COMPOSE_POSTGRES_URL), None),
    C("neg-fp-readme-quickstart-urls", PASS,
      stage_content("README.md", FP_README_QUICKSTART), None),
    C("neg-fp-compose-rabbitmq-guest", PASS,
      stage_content("docker-compose.yml", FP_COMPOSE_RABBITMQ), None),
    C("neg-fp-docs-mongo-root-example", PASS,
      stage_content("docs/setup.md", FP_DOCS_MONGO), None),
    C("neg-fp-docs-curl-admin-admin", PASS,
      stage_content("docs/api.md", FP_DOCS_CURL), None),
    C("neg-fp-aws-doc-example-key-in-test", PASS,
      stage_content("tests/test_s3.py", FP_AWS_DOC_KEY_IN_TEST), None),
    C("neg-fp-env-example-service-placeholders", PASS,
      stage_content(".env.example", FP_ENV_EXAMPLE_SERVICES), None),
    C("neg-fp-compose-localdev-password", PASS,
      stage_content("docker-compose.yml", FP_COMPOSE_LOCALDEV_PASSWORD), None),
    C("neg-fp-js-password-property", PASS,
      stage_content("src/auth.js", FP_JS_PASSWORD_PROPERTY), None),
    C("neg-fp-ts-password-property", PASS,
      stage_content("src/api/client.ts", FP_TS_PASSWORD_PROPERTY), None),
    C("neg-fp-python-password-dict", PASS,
      stage_content("app/serializers.py", FP_PY_PASSWORD_DICT), None),
    C("neg-fp-test-fixture-famous-password", PASS,
      stage_content("tests/conftest.py", FP_TEST_FAMOUS_PASSWORD), None),
    C("neg-fp-terraform-random-password", PASS,
      stage_content("infra/db.tf", FP_TERRAFORM_RANDOM_PASSWORD), None),
    C("neg-fp-helm-values-bitnami-default", PASS,
      stage_content("chart/values.yaml", FP_HELM_BITNAMI_DEFAULT), None),
    C("neg-fp-docs-ptbr-postgres-dev-local", PASS,
      stage_content("docs/variaveis.md", FP_DOCS_PTBR_DEV_LOCAL), None),
    C("neg-fp-django-insecure-secret-key", PASS,
      stage_content("app/settings.py", FP_DJANGO_INSECURE_SECRET_KEY), None),

    # =================================================================
    # PASS -- NO-REGENERATION TRIPWIRE. Every payload below IS a secret
    # (or a placeholder the old rule argued about) and now commits clean,
    # because the generic assignment rule was removed. Asserting them as
    # PASS is how the scope cut is encoded in a test instead of only in
    # prose: re-add a broad value rule and these go red first.
    #
    # This is not a claim that these are safe to commit. It is a claim
    # about WHERE the boundary of this piece is. gitleaks / trufflehog in
    # CI is the layer that covers them.
    # =================================================================
    C("neg-tripwire-punctuated-strong-password", PASS,
      stage_content("config/db.env", b"DB_PASSWORD=Xy!9kLmNp2QrStUvWx\n"), None),
    C("neg-tripwire-quoted-key-json", PASS,
      stage_content("config.json",
                    b'{\n  "password": "hunter2hunter2hunter2"\n}\n'), None),
    C("neg-tripwire-env-example-placeholders", PASS,
      stage_content(".env.example", TRIPWIRE_ENV_EXAMPLE), None),
    C("neg-tripwire-django-env-lookup-and-policy", PASS,
      stage_content("app/settings.py", TRIPWIRE_DJANGO_SETTINGS), None),
    C("neg-tripwire-shell-var-indirection", PASS,
      stage_content("docker-compose.yml",
                    b"    environment:\n"
                    b"      DB_PASSWORD: ${POSTGRES_PASSWORD}\n"
                    b"      API_KEY: $SERVICE_API_KEY\n"), None),
    C("neg-tripwire-ansible-template", PASS,
      stage_content("roles/db/vars.yml",
                    b'  password: "{{ vault_db_password }}"\n'), None),

    # =================================================================
    # PASS -- structural non-secrets. Nothing to do with the scope cut;
    # these keep the plumbing honest.
    # =================================================================
    C("neg-ordinary-source", PASS,
      stage_content("src/hello.py",
                    b"def greet(name):\n    return 'hello, ' + name\n"), None),
    C("neg-docs-prose-password", PASS,
      stage_content("docs/security.md",
                    b"A senha (password) deve ser rotacionada a cada 90 dias"
                    b" pelo time de plataforma.\n"), None),
    # A submodule pointer has no blob at all; blocking it broke every
    # submodule-using repo.
    C("neg-submodule-pointer", PASS, stage_submodule("vendor/lib"), None),
    # Widening the diff-filter to renames must not make renames suspicious.
    C("neg-rename-innocent-to-innocent", PASS,
      stage_rename("settings.txt", "config/app-settings.txt"), None),
    # A real binary must neither trip the scanner nor crash the wide-
    # encoding probe.
    C("neg-binary-blob", PASS,
      stage_content("assets/logo.bin",
                    b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 8), None),
]


def run_case(case_id, expect, stage, forbidden, expect_output):
    repo = lib.make_repo()
    tmp = os.path.dirname(repo)

    setup_err = stage(repo)
    if setup_err:
        return False, "SETUP ERROR: %s" % setup_err, tmp

    r = lib.commit(repo, "corpus case %s" % case_id)
    blocked = r.returncode != 0
    output = (r.stdout or "") + (r.stderr or "")
    rules = " ".join(ln.strip() for ln in output.splitlines()
                     if ln.strip().startswith("BLOCKED"))

    detail = "rc=%d%s" % (r.returncode, (" | " + rules) if rules else "")

    if expect == BLOCK and not blocked:
        return False, "expected BLOCK but the commit went through (%s)" % detail, tmp
    if expect == PASS and blocked:
        return False, "expected PASS but the commit was blocked (%s)" % detail, tmp
    if forbidden and forbidden in output:
        return False, ("hook echoed forbidden text %r into its own output "
                       "(%s)" % (forbidden, detail)), tmp
    if expect_output and expect_output not in output:
        return False, ("output did not carry the promised diagnostic %r "
                       "(%s)" % (expect_output, detail)), tmp
    # The output has to stay pasteable: no absolute path from the dev's
    # machine, ever.
    if repo in output or tmp in output:
        return False, "hook leaked an absolute path into its output (%s)" % detail, tmp

    if not lib.rmtree(tmp):
        # Reported, never swallowed: a scratch tree the runner could not
        # remove is a fact the operator should see, not a silent leftover.
        return True, detail + " | WARN: scratch tree not removed", tmp
    return True, detail, None


def main():
    failures = []
    blocks = sum(1 for c in CASES if c[1] == BLOCK)
    for case_id, expect, stage, forbidden, expect_output in CASES:
        ok, detail, kept = run_case(case_id, expect, stage, forbidden,
                                    expect_output)
        verdict = "ok  " if ok else "FAIL"
        print("%s %-42s expect=%-5s %s" % (verdict, case_id, expect, detail))
        if not ok:
            failures.append((case_id, detail, kept))

    print("")
    print("corpus: %d cases (%d block / %d pass), %d failed"
          % (len(CASES), blocks, len(CASES) - blocks, len(failures)))
    if failures:
        for case_id, detail, kept in failures:
            sys.stderr.write("FAIL %s: %s\n" % (case_id, detail))
            if kept:
                sys.stderr.write("     repo kept for post-mortem: %s\n" % kept)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
