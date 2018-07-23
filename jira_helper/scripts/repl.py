import click
import jira_helper as jh


@click.command()
def main():
    """Start a REPL to pass JQL queries to JIRA"""
    jh.repl()


if __name__ == '__main__':
    main()
