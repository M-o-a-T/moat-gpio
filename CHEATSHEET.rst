Tips
====

How to test
-----------

There aren't any test cases yet. The reason is that most Linux distributions
don't ship the ``gpio-mockup`` module that would allow me to control
pseudo-GPIO pins from user space. Also, libgpiod isn't in Ubuntu stable yet.

You can run the example programs on a Raspberry Pi, if you connect the right
two pins on the expansion header.


To run yapf
-----------

* Show what changes yapf wants to make: ``yapf -rpd setup.py
  moat/gpio tests``

* Apply all changes directly to the source tree: ``yapf -rpi setup.py
  moat/gpio tests``


To make a release
-----------------

* Run ``towncrier`` to collect your release notes.

* Review your release notes.

* Check everything in.

* Double-check it all works, docs build, etc.

* Use ``git tag`` to tag your version.

* ``make pypi``

* Don't forget to ``git push --tags``.
