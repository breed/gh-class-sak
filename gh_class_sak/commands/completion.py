"""completion: print the shell's tab-completion script for gh-class-sak."""

import os
import sys

import click
from click.shell_completion import get_completion_class

from gh_class_sak.core import error, gh_class_sak, output

SHELLS = ("bash", "zsh", "fish")


@gh_class_sak.command("completion")
@click.argument("shell", required=False, type=click.Choice(SHELLS))
def completion(shell):
    """Print the tab-completion script for SHELL (default: your login shell).

    Commands, subcommands, and flags then complete on TAB. Load it from your
    shell's startup file with the line for your shell below.

    \b
    Examples:
      gh-class-sak completion zsh
      echo 'eval "$(gh-class-sak completion zsh)"' >> ~/.zshrc
      echo 'eval "$(gh-class-sak completion bash)"' >> ~/.bashrc
      echo 'gh-class-sak completion fish | source' >> ~/.config/fish/config.fish
    """
    if shell is None:
        shell = os.path.basename(os.environ.get("SHELL", ""))
        if shell not in SHELLS:
            error(f'can\'t tell your shell ("{shell or "unset"}"): name it —'
                  " bash, zsh, or fish")
            sys.exit(2)
    ctx = click.get_current_context()
    complete = get_completion_class(shell)(
        ctx.find_root().command, {}, "gh-class-sak", "_GH_CLASS_SAK_COMPLETE")
    output(complete.source())
