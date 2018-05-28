Tips
====

To run tests
------------

* Install requirements: ``pip install -r ci/test-requirements.txt``
  (possibly in a virtualenv)

* Actually run the tests: ``pytest moat_gpio``


To run yapf
-----------

* Show what changes yapf wants to make: ``yapf -rpd setup.py
  moat_gpio``

* Apply all changes directly to the source tree: ``yapf -rpi setup.py
  moat_gpio``


To make a release
-----------------

* Update the version in ``moat_gpio/_version.py``

* Run ``towncrier`` to collect your release notes.

* Review your release notes.

* Check everything in.

* Double-check it all works, docs build, etc.

* Build your sdist and wheel: ``python setup.py sdist bdist_wheel``

* Upload to PyPI: ``twine upload dist/*``

* Use ``git tag`` to tag your version.

* Don't forget to ``git push --tags``.
