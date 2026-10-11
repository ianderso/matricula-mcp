"""An MCP server for Matricula Online, the church-book portal ICARUS runs.

Matricula (data.matricula-online.eu) publishes the parish registers of
dioceses and archives in Germany, Austria, Poland, Slovenia, Serbia, Italy,
Switzerland, Luxembourg and Bosnia and Herzegovina: baptisms, marriages and
burials, scanned page by page. The server reads its catalogue pages (the
countries, their dioceses and archives, each one's parishes, each parish's
registers, and each register's pages) and its place search, and hands back a
link that opens any page in Matricula's own viewer for a person to read.

It can also be set to save one page image, but that path is off unless the
operator turns it on, which is only for when ICARUS has granted this client
access: Matricula's image host refuses scripted requests. Nothing here writes
anywhere else, and nothing here keeps a family tree.
"""

__version__ = "0.1.0"
