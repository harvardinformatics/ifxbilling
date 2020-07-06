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

DOCKERCOMPOSEFILE = docker-compose.yml
DOCKERCOMPOSEARGS =
# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile test
prod:
	docker build -t $(PRODIMAGE) $(PRODBUILDARGS) .
	docker push $(PRODIMAGE)
up:
	docker build -t $(DRFIMAGE) -f $(DRFFILE) $(DRFBUILDARGS) .
	docker-compose -f $(DOCKERCOMPOSEFILE) $(DOCKERCOMPOSEARGS) up
down:
	docker-compose -f $(DOCKERCOMPOSEFILE) down
# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXAPIDOC) -e -M --force -o "$(SOURCEDIR)" ifxbilling
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
