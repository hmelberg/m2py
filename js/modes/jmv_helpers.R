# Hjelpere for jamovi-modus 2.0. Lastes én gang av ensureJmvLoaded().
# .jmv_serialize går rekursivt gjennom et jmvcore-resultattre og returnerer
# en liste som jsonlite::toJSON kan sende til JS. Bilder blir plassholdere;
# selve grafikken fanges av captureGraphics når print(results) tegner dem,
# i samme rekkefølge som traverseringen her.

`%||%` <- function(a, b) if (is.null(a)) b else a

.jmv_serialize <- function(x) {
  walk <- function(it) {
    if (is.null(it)) return(NULL)
    vis <- tryCatch(it$visible, error = function(e) TRUE)
    if (identical(vis, FALSE)) return(NULL)
    if (inherits(it, 'Image'))
      return(list(type = 'image', title = it$title))
    if (inherits(it, 'Table')) {
      df <- tryCatch(it$asDF, error = function(e) NULL)
      if (is.null(df)) return(NULL)
      cols <- tryCatch(
        unname(lapply(Filter(function(co) !identical(co$visible, FALSE), it$columns),
               function(co) list(
                 name = co$name,
                 title = if (nzchar(co$title %||% '')) co$title else co$name,
                 superTitle = co$superTitle %||% '',
                 format = paste(co$format %||% '', collapse = ',')))),
        error = function(e) lapply(names(df), function(n)
          list(name = n, title = n, superTitle = '', format = '')))
      rows <- lapply(seq_len(nrow(df)), function(i)
        unname(lapply(as.list(df[i, , drop = FALSE]), function(v)
          if (is.numeric(v) && !is.finite(v)) NA else v)))
      notes <- tryCatch(
        unname(lapply(it$notes, function(n) if (is.list(n)) n$note else as.character(n))),
        error = function(e) list())
      return(list(type = 'table', title = it$title, colNames = as.list(names(df)),
                  columns = cols, rows = rows, notes = notes))
    }
    kids <- tryCatch(it$items, error = function(e) NULL)
    if (!is.null(kids)) {
      out <- unname(Filter(Negate(is.null), lapply(kids, walk)))
      if (!length(out)) return(NULL)
      return(list(type = 'group', title = it$title, items = out))
    }
    txt <- tryCatch(paste(capture.output(print(it)), collapse = '\n'),
                    error = function(e) '')
    if (!nzchar(txt)) return(NULL)
    list(type = 'text', title = it$title, text = txt)
  }
  walk(x)
}
