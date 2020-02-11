import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

with open('requirements.txt') as f:
    requirements = f.read().splitlines()

setuptools.setup(
    name="jackrecorder",
    version="0.0.2",
    author="Riccardo Massidda",
    author_email="contact@rmassidda.it",
    description="Minimal recording module for JACK",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/rmassidda/recorder",
    packages=setuptools.find_packages(),
    install_requires=requirements,
    scripts=['scripts/recorder'],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)
