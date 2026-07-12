# dash v2 - webR-adapter (spec 2026-07-12-dash-v2-runtimes-design.md §5).
# Bygger ALDRI DOM: dashboard()/add()/controls() samler deklarasjoner i
# .dash-miljoet. js/dash-webr.js henter .dash_registry_json() etter
# kjoringen, bygger kort via window.Dash, og re-kjorer funksjonskort med
# .dash_run() (async, captureR). All data krysser grensen som JSON.

.dash <- new.env(parent = emptyenv())

.dash_reset <- function() {
  .dash$dashes <- list()
  invisible(NULL)
}
.dash_reset()

# ---- widgets (samme spec-vokabular som python-adapterne) ----

.dash_widget <- function(kind, spec, values = NULL) {
  spec <- spec[!vapply(spec, is.null, logical(1))]
  list(kind = kind, spec = spec, values = values)
}

slider <- function(min, max, step = NULL, default = NULL, label = NULL) {
  .dash_widget("slider", list(min = min, max = max, step = step,
                              default = if (is.null(default)) min else default,
                              label = label))
}

play <- function(min, max, step = NULL, default = NULL, interval = 600,
                 loop = FALSE, label = NULL) {
  .dash_widget("play", list(min = min, max = max, step = step,
                            default = if (is.null(default)) min else default,
                            interval = interval, loop = isTRUE(loop),
                            label = label))
}

dropdown <- function(..., default = NULL, label = NULL) {
  opts <- c(...)
  idx <- if (!is.null(default) && default %in% opts) which(opts == default)[1] - 1 else 0
  # I() paa options: jsonlite auto_unbox maa ikke kollapse en
  # en-elements meny til skalar - JS-siden venter alltid array.
  .dash_widget("dropdown",
               list(options = I(as.character(opts)), index = idx, label = label),
               values = opts)
}

checkbox <- function(default = FALSE, label = NULL) {
  .dash_widget("checkbox", list(default = isTRUE(default), label = label))
}

textfield <- function(default = "", label = NULL) {
  .dash_widget("textfield", list(default = as.character(default), label = label))
}

numberfield <- function(default = 0, min = NULL, max = NULL, step = NULL,
                        label = NULL) {
  .dash_widget("numberfield", list(default = default, min = min, max = max,
                                   step = step, label = label))
}

.dash_is_widget <- function(v) {
  is.list(v) && !is.null(v$kind) && !is.null(v$spec)
}

# Implisitt kwarg->widget, typebasert (spec §5.2):
#   numerisk lengde 2-3 -> slider | character/factor >1 -> dropdown |
#   numerisk >3 -> dropdown | logical(1) -> checkbox |
#   tall(1) -> numberfield | streng(1) -> textfield
# Kant (dokumentert): numerisk meny med 2-3 valg krever eksplisitt dropdown().
.dash_infer <- function(name, value) {
  if (.dash_is_widget(value)) return(value)
  if (is.logical(value) && length(value) == 1) return(checkbox(default = value))
  if (is.numeric(value) && length(value) %in% c(2, 3))
    return(do.call(slider, unname(as.list(value))))
  if ((is.character(value) || is.factor(value)) && length(value) > 1)
    return(dropdown(as.character(value)))
  if (is.numeric(value) && length(value) > 3) return(dropdown(value))
  if (is.numeric(value) && length(value) == 1) return(numberfield(default = value))
  if (is.character(value) && length(value) == 1) return(textfield(default = value))
  stop(sprintf(paste0(
    "dash: kan ikke lage kontroll av %s (type %s, lengde %d). Bruk ",
    "slider()/dropdown()/checkbox()/textfield()/numberfield()/play()."),
    name, class(value)[1], length(value)))
}

.dash_default <- function(w) {
  if (w$kind == "dropdown") return(w$values[[w$spec$index + 1]])
  w$spec$default
}

.dash_from_raw <- function(w, raw) {
  if (w$kind == "dropdown") return(w$values[[as.integer(raw) + 1]])
  if (w$kind %in% c("slider", "numberfield", "play")) return(as.numeric(raw))
  if (w$kind == "checkbox") return(isTRUE(raw))
  as.character(raw)
}

.dash_widget_spec <- function(name, w) {
  c(w$spec, list(type = w$kind, name = name))
}

# ---- payload (spec v1 §5 - rekkefolgen er prioritetsrekkefolgen) ----

.dash_payload <- function(x, unit = NULL, fmt = NULL, ref = NULL, bra = "opp") {
  if (is.null(x)) return(list(kind = "text", text = ""))
  if (inherits(x, "data.frame")) {
    # rows som data.frame: toJSON(dataframe="values") gir array-av-arrays
    return(list(kind = "table", columns = I(as.character(names(x))), rows = x))
  }
  if (is.numeric(x) && length(x) == 1) {
    if (!is.finite(x)) return(list(kind = "text", text = format(x)))
    if (!is.null(ref) && (!is.numeric(ref) || !is.finite(ref))) ref <- NULL
    return(list(kind = "number", value = x,
                unit = if (is.null(unit)) "" else unit,
                fmt = fmt, ref = ref, bra = bra))
  }
  if (is.logical(x) && length(x) == 1) return(list(kind = "text", text = format(x)))
  if (is.character(x) && length(x) == 1) {
    s <- trimws(x)
    if (startsWith(s, "data:image") ||
        grepl("\\.(png|jpe?g|gif|svg|webp)(\\?.*)?$", tolower(s)))
      return(list(kind = "image", src = s))
    return(list(kind = "markdown", text = x))
  }
  list(kind = "text", text = paste(capture.output(print(x)), collapse = "\n"))
}

.dash_payload_json <- function(p) {
  as.character(jsonlite::toJSON(p, dataframe = "values", auto_unbox = TRUE,
                                na = "null", null = "null", digits = NA))
}

# ---- offentlig API ----

dashboard <- function(title = "", layout = NULL) {
  di <- length(.dash$dashes) + 1
  d <- new.env(parent = emptyenv())
  d$title <- title
  d$layout <- layout
  d$cards <- list()
  d$shared <- list()
  .dash$dashes[[di]] <- d

  # Dot-prefiks paa forsteparameteren: brukerens funksjonsparametre kan
  # hete x (d$add(g, x = 5)) uten aa kollidere med adds egen formelle.
  d$add <- function(.x, title = NULL, at = NULL, unit = NULL, fmt = NULL,
                    ref = NULL, bra = "opp", ...) {
    kw <- list(...)
    ci <- length(d$cards) + 1
    if (is.function(.x)) {
      widgets <- list()
      for (n in names(kw)) widgets[[n]] <- .dash_infer(n, kw[[n]])
      d$cards[[ci]] <- list(func = .x, widgets = widgets,
                            params = names(formals(.x)),
                            title = title, at = at, unit = unit, fmt = fmt,
                            ref = ref, bra = bra)
    } else if (inherits(.x, "ggplot")) {
      # statiske plott realiseres via samme captureR-sti som funksjonskort
      d$cards[[ci]] <- list(func = local({ .gg <- .x; function() .gg }),
                            widgets = list(), params = character(0),
                            title = title, at = at, unit = NULL, fmt = NULL,
                            ref = NULL, bra = "opp")
    } else {
      d$cards[[ci]] <- list(payload = .dash_payload(.x, unit = unit, fmt = fmt,
                                                    ref = ref, bra = bra),
                            title = title, at = at)
    }
    invisible(NULL)
  }

  d$controls <- function(...) {
    kw <- list(...)
    for (n in names(kw)) d$shared[[n]] <- .dash_infer(n, kw[[n]])
    invisible(NULL)
  }

  d
}

# ---- grensesnittet js/dash-webr.js bruker ----

.dash_registry_json <- function() {
  dashes <- lapply(.dash$dashes, function(d) {
    cards <- lapply(d$cards, function(card) {
      out <- list(title = card$title, at = card$at)
      if (!is.null(card$func)) {
        out$func <- TRUE
        out$params <- I(as.character(card$params))
        specs <- list()
        for (n in names(card$widgets))
          specs[[length(specs) + 1]] <- .dash_widget_spec(n, card$widgets[[n]])
        out$controls <- specs
      } else {
        out$payload <- card$payload
      }
      out
    })
    shared <- list()
    for (n in names(d$shared))
      shared[[length(shared) + 1]] <- .dash_widget_spec(n, d$shared[[n]])
    list(title = d$title, layout = d$layout, cards = cards, shared = shared)
  })
  as.character(jsonlite::toJSON(list(dashes = dashes), dataframe = "values",
                                auto_unbox = TRUE, na = "null", null = "null",
                                digits = NA))
}

.dash_run <- function(di, ci, values_json) {
  d <- .dash$dashes[[di]]
  card <- d$cards[[ci]]
  raw <- jsonlite::fromJSON(values_json, simplifyVector = FALSE)
  vals <- list()
  for (n in card$params) {
    w <- card$widgets[[n]]
    if (is.null(w)) w <- d$shared[[n]]
    if (is.null(w)) next
    vals[[n]] <- if (!is.null(raw[[n]])) .dash_from_raw(w, raw[[n]])
                 else .dash_default(w)
  }
  res <- tryCatch(do.call(card$func, vals), error = function(e) e)
  if (inherits(res, "error"))
    return(.dash_payload_json(list(kind = "error",
                                   message = conditionMessage(res))))
  if (inherits(res, "ggplot")) {
    print(res)   # tegner -> JS-gluen bruker captureR-bildet
    return(.dash_payload_json(list(kind = "text", text = "")))
  }
  .dash_payload_json(.dash_payload(res, unit = card$unit, fmt = card$fmt,
                                   ref = card$ref, bra = card$bra))
}
