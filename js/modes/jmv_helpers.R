# Hjelpere for jamovi-modus 2.0. Lastes én gang av ensureJmvLoaded().
# .jmv_serialize går rekursivt gjennom et jmvcore-resultattre og returnerer
# en liste som jsonlite::toJSON kan sende til JS. Bilder blir plassholdere;
# selve grafikken fanges av captureGraphics når print(results) tegner dem,
# i samme rekkefølge som traverseringen her.

# jmv::pca()/jmv::efa() sin standardmetode for antall faktorer ('parallel', Horns
# parallellanalyse via psych::fa.parallel) kaller parallel::mclapply() UTEN eksplisitt
# mc.cores - som da faller til getOption('mc.cores', 2L) og prøver ekte fork() (mcfork()).
# webR/wasm har ingen fork()-systemkall ("unable to fork, possible reason: Function not
# implemented"), selv om plattformen rapporterer seg som unix-lignende (så mclapply sin
# vanlige Windows-fallback til lapply ikke slår inn). mclapply(mc.cores=1) er R sin egen,
# dokumenterte seriell-fallback (samme kode-sti som brukes på Windows) - null endring i
# beregnet resultat, bare ingen forking. Sett globalt her, ufarlig for analyser som ikke
# bruker mclapply.
options(mc.cores = 1)

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
      notes <- tryCatch({
        ns <- unname(lapply(it$notes, function(n) if (is.list(n)) (n$note %||% '') else as.character(n)))
        Filter(function(s) nzchar(s), ns)
      }, error = function(e) list())
      return(list(type = 'table', title = it$title, colNames = as.list(names(df)),
                  columns = cols, rows = rows, notes = notes))
    }
    # `it$items` er jmvcore sin "gi alle barn"-aksessor for Group-objekter, MEN jmvcore
    # gir også hvert barn en oppslags-snarvei under sitt eget navn - kolliderer det navnet
    # med selve aksessor-navnet 'items' (f.eks. jmv::reliability sin item-nivå-tabell heter
    # bokstavelig talt 'items'), returnerer it$items DET ENE barnet i stedet for hele lista
    # (bekreftet mot jmvcore-kilden: Group$add() gjør private$.items[[barn$name]] <- barn,
    # en helt normal navngitt liste - kollisjonen ligger i selve $-oppslaget, ikke i lista).
    # Gå derfor rett på det private feltet, som alltid er den ekte barnelisten.
    kids <- tryCatch(it$.__enclos_env__$private$.items, error = function(e) NULL)
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

# jmv::contTables() drar (via vcdExtra -> ca -> htmlwidgets -> webshot2 -> chromote) inn
# pakken 'websocket', som chromote bruker til å fjernstyre en ekte Chrome-nettleser for
# skjermbilder av htmlwidgets. 'websocket' finnes ikke som wasm-binær i webR-repoet, så
# loadNamespace('websocket') feiler alltid der - selv om funksjonaliteten aldri kalles av
# contTables sine beregninger (bekreftet ved å lese chromote sin NAMESPACE: den importerer
# kun websocket::WebSocket, ingenting annet). .jmv_install_stubs() installerer derfor en
# minimal, ren-R stub-pakke som lar navneroms-lastingen lykkes; stubben feiler tydelig hvis
# noen faktisk prøver å bruke den (noe som ikke skjer i vår bruk).
#
# webR støtter ikke install.packages(..., type='source') (ingen R CMD INSTALL/kompilator i
# wasm - "This version of R is not set up to install source packages"), så vi bygger
# "installert pakke"-strukturen for hånd direkte i .libPaths()[1]:
#   DESCRIPTION + NAMESPACE + en lazyload-database (tools:::makeLazyLoadDB, ren R) +
#   standard nspackloader.R-lasteren (identisk i alle installerte R-pakker, kobler
#   loadNamespace() til databasen) + Meta/package.rds (tools:::.split_description).
# Idempotent: hvis requireNamespace() alt lykkes (ekte pakke, eller stub fra forrige kjøring
# i samme webR-økt/lib), gjøres ingenting.
.jmv_stub_specs <- list(
  websocket = list(
    # >= chromote sitt krav (websocket (>= 1.2.0) i Imports); .9000 markerer tydelig at
    # dette er en uferdig/dev-stub, ikke et ekte utgitt versjonsnummer.
    version = '1.2.0.9000',
    title = 'Stub for websocket (mangler som wasm-binær i webR)',
    description = paste(
      'Minimal stub-pakke som lar chromote sin navneroms-lasting lykkes i webR/wasm,',
      'der den ekte websocket-pakken ikke finnes som wasm-binær.',
      'chromote importerer kun websocket::WebSocket, og bruker den utelukkende til å',
      'fjernstyre en ekte Chrome-nettleser for skjermbilder av htmlwidgets - noe',
      'jmv::contTables() sine beregninger aldri kaller. Stubben feiler tydelig hvis',
      'noen faktisk forsøker å bruke den.'),
    exports = 'WebSocket',
    code = paste(
      'WebSocket <- list(new = function(...) stop(',
      '"websocket er ikke tilgjengelig i webR (stub-pakke): fjernstyring av en ekte ',
      'Chrome-nettleser er ikke støttet i wasm.", call. = FALSE))', sep = '')
  )
)

# Innholdet i share/R/nspackloader.R, som R CMD INSTALL normalt legger i R/<pkg> for enhver
# installert pakke. Generisk (leser pakkenavn/libsti fra loadingNamespaceInfo()), så samme
# tekst kan brukes uendret for enhver stub - vi trenger ikke lese den fra en installert pakke.
.jmv_nspackloader <- paste(
  'local({',
  '    info <- loadingNamespaceInfo()',
  '    pkg <- info$pkgname',
  '    ns <- .getNamespace(as.name(pkg))',
  '    if (is.null(ns))',
  '        stop("cannot find namespace environment for ", pkg, domain = NA);',
  '    dbbase <- file.path(info$libname, pkg, "R", pkg)',
  '    lazyLoad(dbbase, ns, filter = function(n) n != ".__NAMESPACE__.")',
  '})', sep = '\n')

.jmv_build_stub_pkg <- function(pkg, spec) {
  libdir <- .libPaths()[1]
  pkgdir <- file.path(libdir, pkg)
  unlink(pkgdir, recursive = TRUE)
  dir.create(file.path(pkgdir, 'R'), recursive = TRUE)
  dir.create(file.path(pkgdir, 'Meta'), recursive = TRUE)

  writeLines(c(
    paste('Package:', pkg),
    'Type: Package',
    paste('Title:', spec$title),
    paste('Version:', spec$version),
    'Authors@R: person("safestat", role = c("aut", "cre"))',
    paste('Description:', spec$description),
    'License: MIT',
    'Encoding: UTF-8',
    # loadNamespace() krever et gyldig 'Built:'-felt ("package has not been installed
    # properly" ellers) - dette er normalt satt av R CMD INSTALL, som vi hopper over.
    sprintf('Built: R %s; ; %s; unix', getRversion(), format(Sys.time(), '%Y-%m-%d %H:%M:%S', tz = 'UTC'))
  ), file.path(pkgdir, 'DESCRIPTION'))

  writeLines(paste0('export(', spec$exports, ')'), file.path(pkgdir, 'NAMESPACE'))

  env <- new.env()
  eval(parse(text = spec$code), envir = env)
  tools:::makeLazyLoadDB(env, file.path(pkgdir, 'R', pkg))
  writeLines(.jmv_nspackloader, file.path(pkgdir, 'R', pkg))

  db <- read.dcf(file.path(pkgdir, 'DESCRIPTION'))[1, ]
  saveRDS(tools:::.split_description(db), file.path(pkgdir, 'Meta', 'package.rds'))
  invisible(NULL)
}

.jmv_install_stubs <- function() {
  for (pkg in names(.jmv_stub_specs)) {
    if (requireNamespace(pkg, quietly = TRUE)) next
    tryCatch(
      .jmv_build_stub_pkg(pkg, .jmv_stub_specs[[pkg]]),
      error = function(e)
        warning(sprintf("Klarte ikke å installere stub for '%s': %s", pkg, conditionMessage(e)))
    )
  }
  invisible(NULL)
}
