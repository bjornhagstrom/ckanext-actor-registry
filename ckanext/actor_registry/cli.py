import click

from ckanext.actor_registry import schema_tool


@click.group("actor-registry", short_help="Actor Registry tools.")
def actor_registry():
    pass


@actor_registry.command("schema", short_help="Write a schema copy that uses the registry's contact points.")
@click.argument("source")
@click.option("-o", "--output", type=click.Path(dir_okay=False, writable=True),
              help="File to write (default: standard output).")
def schema(source, output):
    """Read the Scheming dataset schema SOURCE (module:path, file or URL) and write
    a copy with the registry's contact points (contact_point_ids). The free-text
    contact fields (ckanext-dcat's contact, CKAN's Author and Maintainer) are
    kept as legacy fields, hidden but saved once the migration is closed."""
    try:
        text, note = schema_tool.convert(source)
    except schema_tool.SchemaToolError as error:
        raise click.ClickException(str(error))
    if output:
        try:
            with open(output, "w", encoding="utf-8") as out:
                out.write(text)
        except OSError as error:
            raise click.ClickException("Could not write %s: %s" % (output, error.strerror or error))
        click.echo("%s: %s" % (output, note), err=True)
    else:
        click.echo(text, nl=False)


def get_commands():
    return [actor_registry]
