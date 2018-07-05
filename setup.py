from setuptools import setup, find_packages

exec(open("moat_gpio/_version.py", encoding="utf-8").read())

LONG_DESC = open("README.rst", encoding="utf-8").read()

setup(
    name="moat-gpio",
    version=__version__,
    description="Control GPIO lines via AMQP",
    url="https://github.com/M-o-a-T/",
    long_description=LONG_DESC,
    author="Matthias Urlichs",
    author_email="matthias@urlichs.de",
    license="MIT -or- Apache License 2.0",
    packages=find_packages(exclude="tests"),
    install_requires=[
        "trio-amqp",
        "trio-gpio",
        "trio-click",
    ],
    keywords=[
        "gpio", "amqp",
    ],
    entry_points={
        'console_scripts': [
            'moat-gpiod = moat_gpio.cli:daemon',
            'moat-gpio-set = moat_gpio.cli:set',
        ]
    },
    python_requires=">=3.5",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "License :: OSI Approved :: Apache Software License",
        "Framework :: Trio",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3 :: Only",
        "Development Status :: 3 - Alpha",
        # TODO:
        # - Intended Audience
        # - Topic
        #
        # For the full list of options, see:
        #   https://pypi.python.org/pypi?%3Aaction=list_classifiers
    ],
)
