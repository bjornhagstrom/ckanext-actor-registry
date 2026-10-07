# Organizations, publishers and contact points: common setups

Catalogues are organised in different ways. What is obvious in one catalogue
("the organization *is* the publisher") is wrong in the next. This page
describes the setups we have seen, and how we recommend handling each one with
this extension. If your catalogue does not match any of them, please
[open an issue](https://github.com/bjornhagstrom/ckanext-actor-registry/issues):
we would like to know.

## Three different questions

CKAN has one concept, the organization, where DCAT-AP has three. Keeping them
apart is the key to every setup below.

| Question | Answered by | In DCAT-AP |
|---|---|---|
| Who may edit this dataset? | **Organization** (CKAN core) | not exported as such |
| Who is responsible for making it available? | **Publisher** (this extension) | `dct:publisher` |
| Who do I ask about it? | **Contact points** (this extension) | `dcat:contactPoint` |

Often one body answers all three. The point of the extension is that it does
not have to.

## Publisher setups

| Setup | Example | Recommendation |
|---|---|---|
| **A. One organization, one publisher** | Each agency in a national catalogue is its own organization and publishes its own data | No publisher field needed. The DCAT export uses the organization as publisher. Use `contact_points_only_schema.yaml`. |
| **B. Several organizations, one publisher** | A city's departments are organizations (so each can edit its own datasets), but the city is the publisher | Create one publisher record (the city) and select it on the datasets. |
| **C. One organization, several publishers** | One organization for the whole city, but each committee or board is the publisher of its own data | Create one publisher record per committee. Editors select the right one per dataset; the organization cannot tell which it is. |
| **D. Publisher outside the catalogue** | A regional portal publishes data on behalf of member municipalities, or a company publishes through a public catalogue | Create publisher records for the external bodies. They do not need a CKAN organization or user account. |

Which body is the "right" publisher is a policy decision for your catalogue,
not a technical one. In some countries each committee is legally a separate
authority, yet many catalogues still name the city as publisher. Decide once,
write it down for your editors, and the extension will follow it.

A dataset has at most one publisher. Without one, the DCAT export falls back to
the organization (ckanext-dcat's own behaviour), so setup A needs no data in
the registry at all.

## Contact point setups

| Setup | Example | Recommendation |
|---|---|---|
| **Function mailbox** | "Open Data Desk", opendata@example.org, on many datasets | The main use of the registry: store it once, link it everywhere. |
| **Named person** | A GIS specialist answers for "their" datasets | Works, but people change roles. Prefer a function name ("GIS Support") with the person's address behind it, so the record survives a handover. |
| **Same address, different functions** | gis@example.org answers both as "GIS Support" and as "Map Services" | Allowed: create two contact points with the same email. Only the URI has to be unique. |
| **Several contacts per dataset** | A subject expert and a technical contact | Link both. A dataset can have several contact points. |

## CKAN's own contact fields

CKAN core has Author, Author email, Maintainer and Maintainer email as free
text on each dataset. In CKAN, the **maintainer** is the one you contact, and
the **author** is who created the data. Our recommendation when you move to the
registry:

- **Maintainer** becomes a contact point.
- **Author** becomes a contact point only when there is no maintainer. When both
  exist and differ, an editor decides whether the author is a contact point of
  its own, a publisher, or neither.
- **The original fields are never changed.** Their values stay in the database
  and the API, so the move can always be undone. Hide them in your schema once
  the move is complete.

See [Activating on an existing installation with datasets](../README.md#activating-on-an-existing-installation-with-datasets)
for how to do this today.

## Summary of our recommendations

1. Start from the setup you have, not the one you wish you had. All four
   publisher setups are supported.
2. Use a publisher field only when the publisher can differ from the
   organization (setups B, C and D).
3. Make contact points functions, not people, where you can.
4. Decide the publisher policy once and document it for your editors.
