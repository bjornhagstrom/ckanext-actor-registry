"""Write a copy of a Scheming dataset schema that uses the registry's contact points.

The extension never changes a schema by itself. This tool reads a schema you
already use, such as ``ckanext.dcat.schemas:dcat_ap_full.yaml`` or, for a
catalogue without ckanext-dcat, ``ckanext.scheming:ckan_dataset.yaml`` (CKAN's
own fields), and writes your own copy with the registry's
``contact_point_ids`` where the free-text contact fields were. The old fields
stay in the copy as legacy fields: ckanext-dcat's repeating field ``contact``
with ``legacy_dcat_contact.html``, CKAN's Author, Maintainer and their emails
with ``legacy_contact.html``. They are shown and editable while the migration
is open, then hidden but kept, because CKAN removes a stored value that a
save does not send. Nothing from
the source schema is shipped with this extension; the copy is made from the
version installed where you run it, so run it again after upgrading the source.

Run it as ``ckan actor-registry schema SOURCE`` or, without a CKAN
configuration (in a Docker build, for example), as
``python -m ckanext.actor_registry.schema_tool SOURCE``.
"""

import argparse
import copy
import http.client
import importlib.util
import os
import sys
import urllib.parse
import urllib.request

import yaml

CONTACT_FIELD = "contact"
REGISTRY_FIELD = "contact_point_ids"
# CKAN's own free-text contact fields: without ckanext-dcat's field, the
# registry field goes after the last of these.
CKAN_CONTACT_FIELDS = ("author", "author_email", "maintainer", "maintainer_email")
EXAMPLE_SCHEMA = "ckanext.actor_registry.examples:actor_registry_schema.yaml"


class SchemaToolError(Exception):
    """The schema cannot be read or converted (nothing was written)."""


def read_schema(source):
    """A schema as a dict from ``module:path``, a file path or an http(s) URL."""
    if _without_credentials(source) != source:
        # urllib does not send them (it takes "user:password@host" for a host and port),
        # its error would quote them, and no other source form takes them either.
        raise SchemaToolError("Could not read the schema %s: a user name or password in the URL is not supported; "
                              "download the schema and give its path" % _without_credentials(source))
    try:
        if source.startswith(("http://", "https://")):
            with urllib.request.urlopen(source, timeout=30) as response:  # noqa: S310 (operator-given URL)
                text = response.read().decode("utf-8")
        else:
            with open(_path(source), encoding="utf-8") as schema_file:
                text = schema_file.read()
        schema = yaml.safe_load(text)
    except (OSError, ValueError, http.client.HTTPException, yaml.YAMLError) as error:
        raise SchemaToolError("Could not read the schema %s: %s" % (source, error))
    if not isinstance(schema, dict) or not isinstance(schema.get("dataset_fields"), list):
        raise SchemaToolError("%s is not a Scheming dataset schema (no dataset_fields)" % _without_credentials(source))
    return schema


def _path(source):
    if source.startswith("file://"):  # the form Scheming takes for a file
        return urllib.parse.unquote(urllib.parse.urlsplit(source).path)
    if ":" not in source or os.path.exists(source):
        return source
    module, file_name = source.split(":", 1)
    try:
        spec = importlib.util.find_spec(module)
    except ImportError:  # a parent package is missing (ckanext-dcat not installed, for example)
        spec = None
    if spec is None:
        raise SchemaToolError("No module %s (from %s)" % (module, source))
    if spec.submodule_search_locations:
        base = list(spec.submodule_search_locations)[0]
    else:
        base = os.path.dirname(spec.origin)
    return os.path.join(base, file_name)


def registry_field():
    """The contact points field, as in the extension's example schema."""
    for field in read_schema(EXAMPLE_SCHEMA)["dataset_fields"]:
        if field.get("field_name") == REGISTRY_FIELD:
            return copy.deepcopy(field)
    raise SchemaToolError("The example schema has no %s field" % REGISTRY_FIELD)  # pragma: no cover


LEGACY_SNIPPET = "legacy_dcat_contact.html"
LEGACY_LABEL = {"en": "Contact points (free text)", "sv": "Kontaktpunkter (fritext)",
                "sv_SE": "Kontaktpunkter (fritext)"}


CKAN_LEGACY_SNIPPET = "legacy_contact.html"
# Keys of a CKAN contact field that the legacy snippet replaces: it shows an
# email as a mailto link itself.
CKAN_DISPLAY_KEYS = ("display_email_name_field",)


def with_registry_contact_points(schema):
    """``(new_schema, note)``: a copy of ``schema`` with the registry's contact
    points where the free-text contact fields were; those are kept as legacy
    fields (see the module docstring). The registry field goes right before
    ckanext-dcat's ``contact``; without it after CKAN's own contact fields,
    or last."""
    fields = schema["dataset_fields"]
    names = [field.get("field_name") for field in fields]
    if REGISTRY_FIELD in names:
        raise SchemaToolError("The schema already has the field %s" % REGISTRY_FIELD)
    schema = copy.deepcopy(schema)
    fields = schema["dataset_fields"]
    legacy_names = []
    for field in fields:
        if field.get("field_name") in CKAN_CONTACT_FIELDS:
            field["form_snippet"] = field["display_snippet"] = CKAN_LEGACY_SNIPPET
            field.pop("required", None)  # hidden once the migration is closed: nothing to fill in
            for key in CKAN_DISPLAY_KEYS:
                field.pop(key, None)
            legacy_names.append(field["field_name"])
    if CONTACT_FIELD in names:
        position = names.index(CONTACT_FIELD)
        legacy = fields[position]
        legacy["form_snippet"] = legacy["display_snippet"] = LEGACY_SNIPPET
        legacy["label"] = dict(LEGACY_LABEL)
        legacy.pop("repeating_label", None)
        legacy.pop("required", None)
        legacy_names.insert(0, CONTACT_FIELD)
    else:
        after = [index for index, name in enumerate(names) if name in CKAN_CONTACT_FIELDS]
        position = after[-1] + 1 if after else len(fields)
    fields.insert(position, registry_field())
    if legacy_names:
        return schema, "added the field %s; kept as legacy fields: %s" % (REGISTRY_FIELD, ", ".join(legacy_names))
    return schema, "added the field %s" % REGISTRY_FIELD


def _without_credentials(source):
    """``source`` with any ``user:password@`` of a URL masked, for the file header and messages."""
    parts = urllib.parse.urlsplit(source)
    if parts.scheme and "@" in parts.netloc:
        return urllib.parse.urlunsplit(parts._replace(netloc="***@" + parts.netloc.rsplit("@", 1)[1]))
    return source


def render(schema, source):
    source = _without_credentials(source)
    header = (
        "# Made by ckanext-actor-registry (ckan actor-registry schema) from\n"
        "# %s: the registry's contact points (contact_point_ids), and the\n"
        "# free-text contact fields kept as legacy fields. Run the tool again after\n"
        "# upgrading the source.\n" % source
    )
    return header + yaml.safe_dump(schema, sort_keys=False, allow_unicode=True, width=1000)


def convert(source):
    """``(text, note)`` for ``source``; raises SchemaToolError."""
    schema, note = with_registry_contact_points(read_schema(source))
    return render(schema, source), note


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("source", help="module:path, file or URL of the schema to convert")
    parser.add_argument("-o", "--output", help="file to write (default: standard output)")
    args = parser.parse_args(argv)
    try:
        text, note = convert(args.source)
    except SchemaToolError as error:
        print(str(error), file=sys.stderr)
        return 1
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as out:
                out.write(text)
        except OSError as error:
            print("Could not write %s: %s" % (args.output, error.strerror or error), file=sys.stderr)
            return 1
        print("%s: %s" % (args.output, note), file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
