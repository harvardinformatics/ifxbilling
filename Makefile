# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line.
SPHINXOPTS    =
SPHINXBUILD   = sphinx-build
SPHINXAPIDOC  = sphinx-apidoc
SOURCEDIR     = docs/src
BUILDDIR      = docs/build

PRODIMAGE     = harvardinformatics/ifxbilling:latest
PRODBUILDARGS = --ssh default

DRFIMAGE      = ifxbilling
DRFBUILDARGS  = --ssh default
DRFFILE       = Dockerfile
DRFTARGET     = drf

DOCKERCOMPOSEFILE = docker-compose.yml
DOCKERCOMPOSEARGS =
# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile test docs prod build drf
build: drf
drf:
	docker build -t $(DRFIMAGE) -f $(DRFFILE) $(DRFBUILDARGS) .
migrate:
	docker compose -f $(DOCKERCOMPOSEFILE) run $(DRFTARGET) ./wait-for-it.sh -s -t 120 fiine-drf:80 -- ./manage.py makemigrations; docker compose down --remove-orphans
	docker compose -f $(DOCKERCOMPOSEFILE) run $(DRFTARGET) ./wait-for-it.sh -s -t 120 fiine-drf:80 -- ./manage.py migrate; docker compose down --remove-orphans
test: drf migrate
	docker compose -f $(DOCKERCOMPOSEFILE) run $(DRFTARGET) ./wait-for-it.sh -s -t 120 fiine-drf:80 -- ./manage.py test -v 2; docker compose down --remove-orphans
prod:
	docker build -t $(PRODIMAGE) $(PRODBUILDARGS) .
	docker push $(PRODIMAGE)
up: drf
	docker compose -f $(DOCKERCOMPOSEFILE) $(DOCKERCOMPOSEARGS) up
down:
	docker compose -f $(DOCKERCOMPOSEFILE) down
run: build
	docker compose -f $(DOCKERCOMPOSEFILE) run $(DRFTARGET) /bin/bash
docs:
	docker compose -f $(DOCKERCOMPOSEFILE) run drf make html; docker compose down
# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXAPIDOC) -e -M --force -o "$(SOURCEDIR)" ifxbilling
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
