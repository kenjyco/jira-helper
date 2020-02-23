from setuptools import setup, find_packages


with open('README.rst', 'r') as fp:
    long_description = fp.read()

setup(
    name='jira-helper',
    version='0.0.3',
    description='CLI tools and REPL for passing JQL to a JIRA server and filtering results',
    long_description=long_description,
    author='Ken',
    author_email='kenjyco@gmail.com',
    license='MIT',
    url='https://github.com/kenjyco/jira-helper',
    download_url='https://github.com/kenjyco/jira-helper/tarball/v0.0.3',
    packages=find_packages(),
    install_requires=[
        'chloop',
        'requests',
        'settings-helper',
    ],
    include_package_data=True,
    package_dir={'': '.'},
    package_data={
        '': ['*.ini'],
    },
    entry_points={
        'console_scripts': [
            'jira-repl=jira_helper.scripts.repl:main',
        ],
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.5',
        'Topic :: Software Development :: Libraries',
        'Intended Audience :: Developers',
    ],
    keywords = ['jira', 'helper']
)

