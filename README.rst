================
AntiCompositeBot
================
.. image:: https://img.shields.io/github/actions/workflow/status/AntiCompositeNumber/AntiCompositeBot/pythonapp.yml?branch=master
    :alt: GitHub Workflow Status
    :target: https://github.com/AntiCompositeNumber/AntiCompositeBot/actions
.. image:: https://coveralls.io/repos/github/AntiCompositeNumber/AntiCompositeBot/badge.svg?branch=master
    :alt: Coverage Status
    :target: https://coveralls.io/github/AntiCompositeNumber/AntiCompositeBot?branch=master
.. image:: https://img.shields.io/badge/python-v3.9-blue
    :alt: Python version 3.9
    :target: https://www.python.org/
.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :alt: Code style: black
    :target: https://github.com/psf/black

Collection of various bot tasks running on `Wikimedia Commons`_ and the `English Wikipedia`_ maintained by AntiCompositeNumber. All scripts run on `Wikimedia Toolforge`_ from the `anticompositebot tool`_.

This documentation was last updated on 23 September 2021.

.. _Wikimedia Commons: https://commons.wikimedia.org/wiki/User:AntiCompositeBot
.. _English Wikipedia:  https://en.wikipedia.org/wiki/User:AntiCompositeBot
.. _Wikimedia Toolforge: https://wikitech.wikimedia.org/wiki/Portal:Toolforge
.. _anticompositebot tool: https://admin.toolforge.org/tool/anticompositebot

Active tasks
============
ASNBlock
    Maintains reports of unblocked ranges used by known hosting providers at https://en.wikipedia.org/wiki/User:AntiCompositeBot/ASNBlock.

    :Schedule: Nightly, beginning at 02:30 UTC
    :Start: ``kubectl apply -f etc/asnblock_cron.yaml --validate=true``
    :Run now: ``kubectl create job --from cronjob/anticompositebot.asnblock anticompositebot.asnblock``
    :Stop: ``kubectl delete CronJob anticompositebot.asnblock``
    :Logs: ``kubectl logs job/anticompositebot.asnblock``
    :Config: https://en.wikipedia.org/wiki/User:AntiCompositeBot/ASNBlock/config.json

EssayImpact
    Maintains automated essay impact scores at https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Wikipedia_essays/Assessment/Links

    :Schedule: Once every two weeks at 01:45 UTC
    :Start: ``kubectl apply -f etc/essayimpact_cron.yaml --validate=true``
    :Run now: ``kubectl create job --from cronjob/anticompositebot.essayimpact anticompositebot.essayimpact``
    :Stop: ``kubectl delete CronJob anticompositebot.essayimpact``
    :Logs: ``less ~/logs/essayimpact.log``
    :Config: https://en.wikipedia.org/wiki/User:AntiCompositeBot/EssayImpact/config.json

NoLicense
    Automatically tags recently-upload files without a license on Wikimedia Commons for deletion.

    :Schedule: Hourly
    :Start: ``kubectl apply -f etc/nolicense_cron.yaml --validate=true``
    :Run now: ``kubectl create job --from cronjob/anticompositebot.nolicense-cron anticompositebot.nolicense``
    :Stop: ``kubectl delete CronJob anticompositebot.nolicense-cron``
    :Logs: ``less ~/logs/nolicense.log``

RedWarnUsers
    Maintains report of RedWarn usage at https://en.wikipedia.org/wiki/User:AntiCompositeBot/RedWarn_users

    :Schedule: Weekly at 01:15 UTC
    :Start: ``kubectl apply -f etc/redwarnusers_cron.yaml --validate=true``
    :Run now: ``kubectl create job --from cronjob/anticompositebot.redwarnusers anticompositebot.redwarnusers``
    :Stop: ``kubectl delete CronJob anticompositebot.redwarnusers``

ShouldBeSvg
    Maintains "Top 200 images that should use vector graphics" galleries on Commons. For more information, see `ShouldBeSVG.md <ShouldBeSVG.md>`_.

    :Schedule: Daily at 02:11, 10:11, and 18:11 UTC
    :Start: ``kubectl apply -f etc/should_be_svg_cron.yaml --validate=true``
    :Stop: ``kubectl delete CronJob anticompositebot.should-be-svg``
    :Logs: ``less ~/logs/ShouldBeSvg.log``

uncat
    Writes a list of uncategorized Commons files that are in use on other wikis to https://tools-static.wmflabs.org/anticompositebot/uncat.html

    :Schedule: Weekly at 07:30 UTC
    :Start: ``kubectl apply -f etc/uncat_cron.yaml --validate=true``
    :Run now: ``kubectl create job --from cronjob/anticompositebot.uncat anticompositebot.uncat``
    :Stop: ``kubectl delete CronJob anticompositebot.uncat``

catwatch
    Logs the size of https://commons.wikimedia.org/wiki/Category:Files_with_no_machine-readable_license to https://tools-static.wmflabs.org/anticompositebot/Files_with_no_machine-readable_license.json

    :Schedule: Daily at 00:00 UTC
    :Start: ``kubectl apply -f etc/catwatch_cron.yaml --validate=true``
    :Run now: ``kubectl create job --from cronjob/anticompositebot.catwatch anticompositebot.catwatch``
    :Stop: ``kubectl delete CronJob anticompositebot.catwatch``

Files relating to tasks not on this list are likely not actively maintained. This is likely because they were used for a one-off run that has completed.

Contributing
============
Issues and pull requests for existing tasks are welcome! If you're interested in becoming a co-maintainer, please contact AntiCompositeNumber on Wikipedia or GitHub.

This project is written for Python 3.9 and ``pywikibot``. Most tasks have a ``__version__`` and use a scheme loosely based on `SemVer`_. Please update this when making changes. A patch-level change is anything that would not noticably affect the output of the task. A minor-level change includes any significant changes to how a task runs or the output of a task. Some tasks do not use patch-level versions, in that case minor changes do not need to update the version number.

Dependencies for this project are managed usin Poetry_. You can quickly install all runtime and development dependencies using :code:`poetry install --no-root`.

Please format your code with Black_.

Static type checking is performed using mypy_, although not every file contains type annotations yet. You can run mypy with :code:`mypy src`.

Tests are written and run using pytest_. You can run pytest using :code:`python -m pytest`. To skip some longer-running tests, use :code:`python -m pytest -m "not slow"`. To generate a code coverage report, run :code:`coverage run -m pytest && coverage html`. You can also see the current coverage for the repository on Coveralls_.

GitHub Actions automatically runs tests, type checking, and code style validation for new commits and pull requests.

.. _SemVer: https://semver.org/
.. _Poetry: https://python-poetry.org/
.. _Black: https://github.com/psf/black
.. _mypy: https://mypy.readthedocs.io/en/stable/index.html
.. _pytest: https://docs.pytest.org/en/stable/
.. _Coveralls: https://coveralls.io/github/AntiCompositeNumber/AntiCompositeBot?branch=master

Maintaining
===========
These tasks are maintained by AntiCompositeNumber. If you're interested in becoming a co-maintainer, please contact AntiCompositeNumber on Wikipedia or GitHub.

Deploying code
    Code must be deployed to Toolforge manually. Unless a dependency has changed, code can be deployed by SSHing to Toolforge and running the following commands::

        $ become anticompositebot
        $ git -C AntiCompositeBot pull

    Kubernetes will automatically load the new code for the next run.

Updating dependencies
    Dependencies are managed using Poetry_, but are installed on Toolforge using `µPipenv`_. Dependabot will automatically create pull requests if a dependency is out of date. To manually update all dependencies, run the following::

        $ poetry update && git commit -a -m "Update dependencies" && git push

    Then SSH to Toolforge and run the following::

        $ become anticompositebot
        $ webservice shell
        $ cd AntiCompositeBot
        $ ./upgrade.sh

    ``pip`` (or ``micropipenv`` or ``upgrade.sh``)must always be run from within ``webservice shell``. The Toolforge bastion runs Python 3.5, but the Kubernetes containers used to run the bot use Python 3.9. Virtual environments created in Python 3.5 won't run correctly in Python 3.9.

.. _`µPipenv`: https://github.com/thoth-station/micropipenv
