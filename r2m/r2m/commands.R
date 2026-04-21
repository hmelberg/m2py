# commands.R — dplyr verb handlers and regression/plot command translators.
# Each handler returns list(lines = character, warnings = character) or NULL.

# Aggregation function map: R name → microdata stat keyword
AGG_STAT_MAP <- list(
  mean = "mean", sum = "sum", sd = "sd", median = "median",
  min = "min", max = "max", n = "count", IQR = "iqr",
  var = NULL, n_distinct = NULL, first = NULL, last = NULL
)

# Helper: get arg by name or position from a named list
.arg <- function(args, pos, name = NULL) {
  if (!is.null(name) && name %in% names(args)) return(args[[name]])
  # positional: skip args that already have a different name
  unnamed_idx <- which(names(args) == "" | is.na(names(args)))
  if (pos <= length(unnamed_idx)) return(args[[ unnamed_idx[pos] ]])
  NULL
}

# Helper: extract a vector of column name strings from c("x","y"), df[,c(...)], c(x,y)
.extract_col_vector <- function(node, df_name) {
  if (is.null(node)) return(NULL)
  if (is.call(node) && as.character(node[[1]]) == "c") {
    cols <- lapply(as.list(node)[-1], function(a) {
      if (is.character(a)) a
      else if (is.name(a))  as.character(a)
      else col_from_node(a, df_name)
    })
    if (!any(sapply(cols, is.null))) return(unlist(cols))
  }
  if (is.call(node) && as.character(node[[1]]) == "[") {
    sub_args <- as.list(node)[-1]
    if (length(sub_args) >= 2)
      return(.extract_col_vector(sub_args[[length(sub_args)]], df_name))
  }
  col <- col_from_node(node, df_name)
  if (!is.null(col)) return(col)
  if (is.name(node)) return(as.character(node))
  NULL
}

# Helper: translate c(1,2,"a","b") into a character vector via translate_expr
.extract_atomic_vector <- function(node, df_name) {
  if (is.null(node)) return(NULL)
  if (is.call(node) && as.character(node[[1]]) == "c") {
    vals <- sapply(as.list(node)[-1], translate_expr, df_name = df_name)
    if (!any(sapply(vals, is.null))) return(unlist(vals))
  }
  v <- translate_expr(node, df_name)
  if (!is.null(v)) return(v)
  NULL
}

# Helper: parse a dplyr by= argument → list(cols, warning)
.parse_by_cols <- function(by_node) {
  if (is.null(by_node)) return(list(cols = NULL, warning = "// join: no by= specified"))
  if (is.character(by_node)) {
    nms <- names(by_node)
    if (!is.null(nms) && any(nzchar(nms)))
      return(list(cols = nms[nzchar(nms)],
                  warning = "// join: key names differ between datasets — verify merge by()"))
    return(list(cols = unname(by_node), warning = NULL))
  }
  if (is.call(by_node)) {
    fn <- as.character(by_node[[1]])
    if (fn == "c") {
      cargs <- as.list(by_node)[-1]
      nms   <- names(cargs)
      cols  <- sapply(cargs, function(a) if (is.character(a)) a else as.character(a))
      if (!is.null(nms) && any(nzchar(nms)))
        return(list(cols = ifelse(nzchar(nms), nms, cols),
                    warning = "// join: key names differ — verify merge by()"))
      return(list(cols = unname(cols), warning = NULL))
    }
    if (sub("^.*::", "", fn) == "join_by") {
      cols <- sapply(as.list(by_node)[-1],
                     function(a) if (is.name(a)) as.character(a) else deparse(a))
      return(list(cols = cols, warning = NULL))
    }
  }
  list(cols = NULL, warning = "// join: could not parse by= argument")
}

# Expander: factor(x, levels=c(...), labels=c(...)) → define-labels + assign-labels
.expand_factor_labels <- function(col, cargs, df_name) {
  x_node     <- if (length(cargs) >= 1) cargs[[1]] else NULL
  levels_arg <- cargs[["levels"]] %||% (if (length(cargs) >= 2) cargs[[2]] else NULL)
  labels_arg <- cargs[["labels"]] %||% (if (length(cargs) >= 3) cargs[[3]] else NULL)

  if (is.null(levels_arg) || is.null(labels_arg))
    return(list(lines = character(0),
                warnings = paste0("// factor(): need levels= and labels= for ", col)))

  lvls <- .extract_atomic_vector(levels_arg, df_name)
  lbls <- .extract_atomic_vector(labels_arg, df_name)

  if (is.null(lvls) || is.null(lbls) || length(lvls) != length(lbls))
    return(list(lines = character(0),
                warnings = paste0("// factor(): mismatched levels/labels for ", col)))

  lbl_name <- paste0(col, "_lbl")
  pairs    <- paste(mapply(function(l, b) paste0(l, "=", b), lvls, lbls), collapse = " ")

  src_col <- if (!is.null(x_node))
    col_from_node(x_node, df_name) %||% (if (is.name(x_node)) as.character(x_node) else NULL)
  else NULL

  lines <- character(0)
  if (!is.null(src_col) && src_col != col)
    lines <- c(lines, paste0("generate ", col, " = ", src_col))
  lines <- c(lines,
             paste0("define-labels ", lbl_name, " ", pairs),
             paste0("assign-labels ", col, " ", lbl_name))
  list(lines = lines, warnings = character(0))
}

# ── filter / keep if ──────────────────────────────────────────────────────────

handle_filter <- function(args, df_name, group_by = NULL) {
  parts <- sapply(args, function(a) translate_expr(a, df_name))
  if (any(sapply(parts, is.null))) {
    failed <- which(sapply(parts, is.null))
    return(list(
      lines    = paste0("// filter: could not translate condition: ",
                        deparse(args[[failed[1]]])),
      warnings = character(0)
    ))
  }
  cond <- if (length(parts) == 1) parts[[1]]
          else paste(sapply(parts, function(p) paste0("(", p, ")")), collapse = " & ")
  list(lines = paste0("keep if ", cond), warnings = character(0))
}

# ── mutate / generate ─────────────────────────────────────────────────────────

handle_mutate <- function(args, df_name, group_by = NULL) {
  agg_specs <- character(0)   # "(stat) src -> tgt" fragments for aggregate command
  gen_lines <- character(0)   # generate/replace lines (non-aggregate)
  warnings  <- character(0)
  nms       <- names(args)

  for (i in seq_along(args)) {
    col <- if (!is.null(nms) && nzchar(nms[i])) nms[i] else NULL
    if (is.null(col)) {
      warnings <- c(warnings, paste0("// mutate: no column name for arg ", i))
      next
    }
    node  <- args[[i]]
    fn    <- if (is.call(node)) as.character(node[[1]]) else ""
    cargs <- if (is.call(node)) as.list(node)[-1] else list()

    # ifelse / if_else → generate + replace
    if (fn %in% c("ifelse", "if_else")) {
      r <- .expand_ifelse(col, cargs, df_name)
      gen_lines <- c(gen_lines, r$lines)
      warnings  <- c(warnings,  r$warnings)
      next
    }

    # case_when → generate . + multiple replace … if
    if (fn == "case_when") {
      r <- .expand_case_when(col, cargs, df_name)
      gen_lines <- c(gen_lines, r$lines)
      warnings  <- c(warnings,  r$warnings)
      next
    }

    # dplyr::recode(col, old = new, ...) when target == source → recode command
    if (fn %in% c("recode", "dplyr::recode")) {
      src <- col_from_node(cargs[[1]], df_name) %||%
             (if (is.name(cargs[[1]])) as.character(cargs[[1]]) else NULL)
      if (!is.null(src) && src == col) {
        r <- .expand_recode(col, cargs[-1], df_name)
        gen_lines <- c(gen_lines, r$lines)
        warnings  <- c(warnings,  r$warnings)
        next
      }
    }

    # coalesce(x, fallback) → replace col = fallback if sysmiss(col)
    if (fn %in% c("coalesce", "dplyr::coalesce")) {
      r <- .expand_coalesce(col, cargs, df_name)
      gen_lines <- c(gen_lines, r$lines)
      warnings  <- c(warnings,  r$warnings)
      next
    }

    # factor(x, levels=c(...), labels=c(...)) → define-labels + assign-labels
    if (fn == "factor") {
      r <- .expand_factor_labels(col, cargs, df_name)
      if (length(r$lines) > 0 || length(r$warnings) > 0) {
        gen_lines <- c(gen_lines, r$lines)
        warnings  <- c(warnings,  r$warnings)
        next
      }
    }

    # as.numeric(col) / as.double(col) where target == source → destring
    if (fn %in% c("as.numeric", "as.double") && length(cargs) == 1) {
      src <- col_from_node(cargs[[1]], df_name) %||%
             (if (is.name(cargs[[1]])) as.character(cargs[[1]]) else NULL)
      if (!is.null(src) && src == col) {
        gen_lines <- c(gen_lines, paste0("destring ", col))
        next
      }
    }

    # group_by context: mean(x) → accumulate aggregate spec
    if (!is.null(group_by) && fn %in% names(AGG_STAT_MAP)) {
      stat <- AGG_STAT_MAP[[fn]]
      if (!is.null(stat) && length(cargs) >= 1) {
        src <- translate_expr(cargs[[1]], df_name)
        if (!is.null(src)) {
          agg_specs <- c(agg_specs, paste0("(", stat, ") ", src, " -> ", col))
          next
        }
      }
    }

    # general expression
    val <- translate_expr(node, df_name)
    if (!is.null(val)) {
      gen_lines <- c(gen_lines, paste0("generate ", col, " = ", val))
    } else {
      warnings <- c(warnings, paste0("// mutate: cannot translate ", col,
                                     " = ", deparse(node)))
    }
  }

  # emit one aggregate command (if any agg specs), then generate lines
  agg_line <- if (length(agg_specs) > 0)
    paste0("aggregate ", paste(agg_specs, collapse = " "), ", by(", group_by, ")")
  else
    character(0)

  list(lines = c(agg_line, gen_lines), warnings = warnings)
}

.expand_ifelse <- function(col, cargs, df_name) {
  if (length(cargs) < 3)
    return(list(lines = character(0), warnings = paste0("// ifelse: too few args for ", col)))
  cond  <- translate_expr(cargs[[1]], df_name)
  tval  <- translate_expr(cargs[[2]], df_name)
  fval  <- translate_expr(cargs[[3]], df_name)
  if (is.null(cond) || is.null(tval) || is.null(fval))
    return(list(lines = character(0), warnings = paste0("// ifelse: untranslatable for ", col)))
  list(
    lines    = c(paste0("generate ", col, " = ", fval),
                 paste0("replace ",  col, " = ", tval, " if ", cond)),
    warnings = character(0)
  )
}

.expand_case_when <- function(col, cargs, df_name) {
  lines <- paste0("generate ", col, " = .")
  warns <- character(0)
  for (cw in cargs) {
    if (!is.call(cw) || as.character(cw[[1]]) != "~") next
    cond_node <- cw[[2]]
    val_node  <- cw[[3]]
    val <- translate_expr(val_node, df_name)
    if (is.null(val)) { warns <- c(warns, paste0("// case_when: untranslatable value for ", col)); next }
    is_default <- (is.name(cond_node) && as.character(cond_node) %in% c("TRUE", "T")) ||
                  (is.logical(cond_node) && isTRUE(cond_node))
    if (is_default) {
      lines <- c(lines, paste0("replace ", col, " = ", val, " if sysmiss(", col, ")"))
    } else {
      cond <- translate_expr(cond_node, df_name)
      if (!is.null(cond)) {
        lines <- c(lines, paste0("replace ", col, " = ", val, " if ", cond))
      } else {
        warns <- c(warns, paste0("// case_when: untranslatable condition for ", col))
      }
    }
  }
  list(lines = lines, warnings = warns)
}

.expand_recode <- function(col, pairs, df_name) {
  nms <- names(pairs)
  if (is.null(nms) || !any(nzchar(nms)))
    return(list(lines = character(0), warnings = paste0("// recode: no names found for ", col)))
  pair_strs <- sapply(seq_along(pairs), function(j) {
    val <- translate_expr(pairs[[j]], df_name)
    if (is.null(val)) return(NULL)
    paste0("(", nms[j], "=", val, ")")
  })
  if (any(sapply(pair_strs, is.null)))
    return(list(lines = character(0), warnings = paste0("// recode: untranslatable values for ", col)))
  list(lines = paste0("recode ", col, " ", paste(pair_strs, collapse = " ")),
       warnings = character(0))
}

.expand_coalesce <- function(col, cargs, df_name) {
  if (length(cargs) < 2)
    return(list(lines = character(0),
                warnings = paste0("// coalesce: need >= 2 arguments for ", col)))
  x_node  <- cargs[[1]]
  fb_node <- cargs[[2]]
  x_col   <- col_from_node(x_node, df_name) %||%
             (if (is.name(x_node)) as.character(x_node) else NULL)
  fb_val  <- translate_expr(fb_node, df_name)
  if (is.null(fb_val))
    return(list(lines = character(0),
                warnings = paste0("// coalesce: untranslatable fallback for ", col)))
  lines <- character(0)
  if (is.null(x_col) || x_col != col) {
    x_val <- translate_expr(x_node, df_name)
    if (is.null(x_val))
      return(list(lines = character(0),
                  warnings = paste0("// coalesce: untranslatable source for ", col)))
    lines <- c(lines, paste0("generate ", col, " = ", x_val))
  }
  lines <- c(lines, paste0("replace ", col, " = ", fb_val, " if sysmiss(", col, ")"))
  list(lines = lines, warnings = character(0))
}

# ── select / keep or drop ────────────────────────────────────────────────────

handle_select <- function(args, df_name, group_by = NULL) {
  pos_cols <- character(0)
  neg_cols <- character(0)
  for (a in args) {
    if (is.call(a) && as.character(a[[1]]) == "-") {
      inner <- as.list(a)[[2]]
      if (is.call(inner) && as.character(inner[[1]]) == "c") {
        neg_cols <- c(neg_cols, sapply(as.list(inner)[-1], as.character))
      } else {
        neg_cols <- c(neg_cols, as.character(inner))
      }
    } else if (is.name(a)) {
      pos_cols <- c(pos_cols, as.character(a))
    } else if (is.character(a)) {
      pos_cols <- c(pos_cols, a)
    }
  }
  if (length(neg_cols) > 0)
    return(list(lines = paste0("drop ", paste(neg_cols, collapse = " ")), warnings = character(0)))
  if (length(pos_cols) > 0)
    return(list(lines = paste0("keep ", paste(pos_cols, collapse = " ")), warnings = character(0)))
  list(lines = character(0), warnings = "// select: could not parse columns")
}

# ── rename ────────────────────────────────────────────────────────────────────

handle_rename <- function(args, df_name, group_by = NULL) {
  nms   <- names(args)
  lines <- character(0)
  for (i in seq_along(args)) {
    if (!is.null(nms) && nzchar(nms[i])) {
      old <- as.character(args[[i]])
      new <- nms[i]
      lines <- c(lines, paste0("rename ", old, " ", new))
    }
  }
  list(lines = lines, warnings = character(0))
}

# ── summarise / collapse ──────────────────────────────────────────────────────

handle_summarise <- function(args, df_name, group_by = NULL) {
  warnings <- character(0)
  nms      <- names(args)
  by_str   <- if (!is.null(group_by)) paste0(", by(", group_by, ")") else ""
  specs    <- character(0)   # accumulate "(stat) src -> tgt" fragments

  for (i in seq_along(args)) {
    new_col <- if (!is.null(nms) && nzchar(nms[i])) nms[i] else NULL
    if (is.null(new_col)) next
    node  <- args[[i]]
    fn    <- if (is.call(node)) as.character(node[[1]]) else ""
    cargs <- if (is.call(node)) as.list(node)[-1] else list()

    # n() → count
    if (fn == "n" && length(cargs) == 0) {
      specs <- c(specs, paste0("(count) ", new_col, " -> ", new_col))
      next
    }
    # n_distinct(x) → no direct equivalent
    if (fn == "n_distinct") {
      warnings <- c(warnings, paste0("// n_distinct() has no microdata equivalent: ", new_col))
      next
    }

    stat <- AGG_STAT_MAP[[fn]]
    if (!is.null(stat)) {
      src <- if (length(cargs) >= 1) translate_expr(cargs[[1]], df_name) else NULL
      if (!is.null(src)) {
        specs <- c(specs, paste0("(", stat, ") ", src, " -> ", new_col))
        next
      }
    }

    # fallback
    val <- translate_expr(node, df_name)
    msg <- if (!is.null(val)) val else deparse(node)
    warnings <- c(warnings, paste0("// summarise: cannot translate ", new_col, " = ", msg))
  }

  lines <- if (length(specs) > 0)
    paste0("collapse ", paste(specs, collapse = " "), by_str)
  else
    character(0)

  list(lines = lines, warnings = warnings)
}

# ── arrange ───────────────────────────────────────────────────────────────────

handle_arrange <- function(args, df_name, group_by = NULL) {
  list(lines = "// arrange: no microdata equivalent", warnings = character(0))
}

# ── drop_na ───────────────────────────────────────────────────────────────────

handle_drop_na <- function(args, df_name, group_by = NULL) {
  if (length(args) == 0)
    return(list(lines = "// drop_na(): drop rows with any missing — translate manually",
                warnings = character(0)))
  conds <- sapply(args, function(a) paste0("sysmiss(", as.character(a), ")"))
  cond  <- paste(sapply(conds, function(c) paste0("(", c, ")")), collapse = " | ")
  list(lines = paste0("drop if ", cond), warnings = character(0))
}

# ── distinct / slice ──────────────────────────────────────────────────────────

handle_distinct <- function(args, df_name, group_by = NULL)
  list(lines = "// distinct: no microdata equivalent", warnings = character(0))

handle_slice_head <- function(args, df_name, group_by = NULL) {
  n_node <- args[["n"]] %||% (if (length(args) >= 1) args[[1]] else NULL)
  n_val  <- if (!is.null(n_node)) as.character(n_node) else "."
  list(lines = paste0("// slice_head(n = ", n_val, "): use 'sample' if needed"),
       warnings = character(0))
}

# ── regression models ─────────────────────────────────────────────────────────

handle_lm <- function(args, df_name) {
  f_node <- args[["formula"]] %||% args[[1]]
  if (is.null(f_node)) return(NULL)
  parts <- .parse_formula(f_node, df_name)
  if (is.null(parts)) return(list(lines = "// lm: could not parse formula", warnings = character(0)))
  list(
    lines    = c(parts$preamble, paste0("regress ", parts$lhs, " ", paste(parts$rhs, collapse = " "))),
    warnings = parts$warnings
  )
}

handle_glm <- function(args, df_name) {
  f_node      <- args[["formula"]] %||% args[[1]]
  family_node <- args[["family"]]  %||% (if (length(args) >= 2) args[[2]] else NULL)
  if (is.null(f_node)) return(NULL)

  cmd <- "regress"
  if (!is.null(family_node)) {
    fam_str <- deparse(family_node)
    if (grepl("binomial", fam_str, ignore.case = TRUE)) {
      cmd <- if (grepl("probit", fam_str, ignore.case = TRUE)) "probit" else "logit"
    } else if (grepl("poisson", fam_str, ignore.case = TRUE)) cmd <- "poisson"
    else if (grepl("Gamma|gamma", fam_str)) {
      return(list(lines = "// glm(family = Gamma): no direct microdata equivalent",
                  warnings = character(0)))
    }
  }
  parts <- .parse_formula(f_node, df_name)
  if (is.null(parts)) return(list(lines = "// glm: could not parse formula", warnings = character(0)))
  list(
    lines    = c(parts$preamble, paste0(cmd, " ", parts$lhs, " ", paste(parts$rhs, collapse = " "))),
    warnings = parts$warnings
  )
}

# glm with family = "probit" link
handle_glm_probit <- function(args, df_name) {
  args[["family"]] <- quote(binomial(link = "probit"))
  r <- handle_glm(args, df_name)
  if (!is.null(r)) r$lines[length(r$lines)] <- sub("^logit ", "probit ", r$lines[length(r$lines)])
  r
}

# ── formula parser ────────────────────────────────────────────────────────────

.parse_formula <- function(node, df_name) {
  if (!is.call(node) || as.character(node[[1]]) != "~") return(NULL)
  lhs <- as.character(node[[2]])
  rhs_node <- node[[3]]

  preamble <- character(0)
  warnings <- character(0)
  counter  <- 0L

  terms_raw <- .formula_terms(rhs_node)
  rhs <- character(0)

  for (term in terms_raw) {
    if (term %in% c("1", "0", "-1")) next  # intercept markers

    # I(expr) → generate _r2m_t<n> = <expr>
    if (startsWith(term, "I(") && endsWith(term, ")")) {
      counter <- counter + 1L
      tmp <- paste0("_r2m_t", counter)
      inner_str <- substr(term, 3, nchar(term) - 1)
      inner_expr <- tryCatch(
        translate_expr(parse(text = inner_str)[[1]], df_name),
        error = function(e) NULL
      )
      if (!is.null(inner_expr)) {
        preamble <- c(preamble, paste0("generate ", tmp, " = ", inner_expr))
      } else {
        preamble <- c(preamble, paste0("generate ", tmp, " = ", inner_str))
        warnings <- c(warnings, paste0("// I() expression may need manual check: ", inner_str))
      }
      rhs <- c(rhs, tmp)
      next
    }

    # x:z interaction → generate _r2m_x_z = x * z
    if (grepl(":", term, fixed = TRUE)) {
      parts <- strsplit(term, ":", fixed = TRUE)[[1]]
      tmp   <- paste0("_r2m_", paste(parts, collapse = "_"))
      preamble <- c(preamble, paste0("generate ", tmp, " = ",
                                     paste(parts, collapse = " * ")))
      rhs <- c(rhs, tmp)
      next
    }

    rhs <- c(rhs, term)
  }

  list(lhs = lhs, rhs = rhs, preamble = preamble, warnings = warnings)
}

.formula_terms <- function(node) {
  if (is.name(node)) return(as.character(node))
  if (is.numeric(node)) return(as.character(node))
  if (!is.call(node)) return(deparse(node))
  fn <- as.character(node[[1]])
  if (fn == "+") return(c(.formula_terms(node[[2]]), .formula_terms(node[[3]])))
  if (fn == "-") {
    if (length(as.list(node)) == 3) {
      return(setdiff(.formula_terms(node[[2]]), .formula_terms(node[[3]])))
    }
    return("-1")
  }
  if (fn == ":") {
    l <- .formula_terms(node[[2]])
    r <- .formula_terms(node[[3]])
    return(paste0(l, ":", r))
  }
  if (fn == "*") {
    l <- .formula_terms(node[[2]])
    r <- .formula_terms(node[[3]])
    return(c(l, r, paste0(l, ":", r)))
  }
  if (fn == "I") return(paste0("I(", deparse(node[[2]]), ")"))
  deparse(node)
}

# ── ggplot2 chain handler ─────────────────────────────────────────────────────

# Flatten a ggplot2 `+` composition into a flat list of component calls
.flatten_gg_chain <- function(node) {
  if (!is.call(node)) return(list(node))
  if (as.character(node[[1]]) == "+")
    return(c(.flatten_gg_chain(node[[2]]), .flatten_gg_chain(node[[3]])))
  list(node)
}

# TRUE when node is a ggplot2 `+` chain containing a ggplot() call
.is_ggplot_chain <- function(node) {
  if (!is.call(node) || as.character(node[[1]]) != "+") return(FALSE)
  parts <- .flatten_gg_chain(node)
  any(sapply(parts, function(p)
    is.call(p) && sub("^.*::", "", as.character(p[[1]])) == "ggplot"
  ))
}

# Extract named aes() mappings → named list of column name strings
.parse_aes <- function(aes_node, df_name) {
  if (!is.call(aes_node)) return(list())
  if (sub("^.*::", "", as.character(aes_node[[1]])) != "aes") return(list())
  aes_args <- as.list(aes_node)[-1]
  nms <- names(aes_args)
  result <- list()
  for (i in seq_along(aes_args)) {
    key <- if (!is.null(nms) && nzchar(nms[i])) nms[i] else as.character(i)
    val <- col_from_node(aes_args[[i]], df_name) %||%
           (if (is.name(aes_args[[i]])) as.character(aes_args[[i]]) else NULL)
    if (!is.null(val)) result[[key]] <- val
  }
  result
}

handle_ggplot_chain <- function(node, df_name) {
  parts    <- .flatten_gg_chain(node)
  fn_names <- sapply(parts, function(p)
    if (is.call(p)) sub("^.*::", "", as.character(p[[1]])) else ""
  )

  # --- ggplot() base call: extract aes ---
  gg_idx <- which(fn_names == "ggplot")[1]
  if (is.na(gg_idx)) return(NULL)
  aes <- list()
  for (a in as.list(parts[[gg_idx]])[-1]) {
    if (is.call(a) && sub("^.*::", "", as.character(a[[1]])) == "aes") {
      aes <- .parse_aes(a, df_name); break
    }
  }

  # --- primary geom ---
  KNOWN_GEOMS <- c("geom_histogram", "geom_density", "geom_freqpoly",
                   "geom_bar", "geom_col",
                   "geom_boxplot", "geom_violin",
                   "geom_point", "geom_jitter", "geom_hex", "geom_bin2d",
                   "geom_line", "geom_smooth", "geom_path")
  geom_idx <- which(fn_names %in% KNOWN_GEOMS)
  if (length(geom_idx) == 0)
    return(list(lines = "// ggplot: no recognised geom layer", warnings = character(0)))
  geom      <- fn_names[geom_idx[1]]
  geom_args <- as.list(parts[[geom_idx[1]]])[-1]

  # merge geom-level aes (geom overrides base only for missing keys)
  for (a in geom_args) {
    if (is.call(a) && sub("^.*::", "", as.character(a[[1]])) == "aes") {
      for (k in names(.parse_aes(a, df_name)))
        if (is.null(aes[[k]])) aes[[k]] <- .parse_aes(a, df_name)[[k]]
      break
    }
  }

  x_var    <- aes[["x"]]
  y_var    <- aes[["y"]]
  fill_var <- aes[["fill"]] %||% aes[["color"]] %||% aes[["colour"]]
  has_flip <- "coord_flip" %in% fn_names

  # facet_wrap(~var) / facet_wrap(vars(var)) → by(var)
  facet_by <- NULL
  for (fi in which(fn_names %in% c("facet_wrap", "facet_grid"))) {
    fa <- as.list(parts[[fi]])[-1]
    if (length(fa) >= 1) {
      f <- fa[[1]]
      if (is.call(f) && as.character(f[[1]]) == "~") {
        facet_by <- as.character(f[[length(f)]])   # last node after ~
      } else if (is.call(f) &&
                 sub("^.*::", "", as.character(f[[1]])) == "vars") {
        facet_by <- paste(sapply(as.list(f)[-1], as.character), collapse = " ")
      }
    }
    break
  }

  # ── histogram / density ──────────────────────────────────────────────────
  if (geom %in% c("geom_histogram", "geom_density", "geom_freqpoly")) {
    if (is.null(x_var))
      return(list(lines = "// ggplot geom_histogram: no x aesthetic", warnings = character(0)))
    opts <- character(0)
    if (!is.null(facet_by)) opts <- c(opts, paste0("by(", facet_by, ")"))
    bins_arg <- geom_args[["bins"]]
    if (!is.null(bins_arg) && is.numeric(bins_arg))
      opts <- c(opts, paste0("bin(", as.integer(bins_arg), ")"))
    bw_arg <- geom_args[["binwidth"]]
    if (!is.null(bw_arg) && is.numeric(bw_arg))
      opts <- c(opts, paste0("width(", bw_arg, ")"))
    cmd <- paste0("histogram ", x_var)
    if (length(opts) > 0) cmd <- paste0(cmd, ", ", paste(opts, collapse = " "))
    return(list(lines = cmd, warnings = character(0)))
  }

  # ── barchart (or piechart when coord_polar("y") is present) ─────────────
  if (geom %in% c("geom_bar", "geom_col")) {
    if ("coord_polar" %in% fn_names) {
      cp_idx  <- which(fn_names == "coord_polar")[1]
      cp_args <- as.list(parts[[cp_idx]])[-1]
      theta   <- if (length(cp_args) >= 1) (cp_args[["theta"]] %||% cp_args[[1]]) else NULL
      if (is.null(theta) || (is.character(theta) && theta == "y")) {
        var <- fill_var %||% x_var
        if (!is.null(var))
          return(list(lines = paste0("piechart ", var), warnings = character(0)))
      }
    }
    stat_kw <- if (geom == "geom_col") "mean" else "count"
    pos_arg <- geom_args[["position"]]
    has_stack <- !is.null(pos_arg) &&
      ((is.character(pos_arg) && pos_arg == "stack") ||
       (is.call(pos_arg) && sub("^.*::", "", as.character(pos_arg[[1]])) == "position_stack"))

    # geom_col or stat="identity": y is the value, x is the grouping
    if (stat_kw == "mean" && !is.null(x_var) && !is.null(y_var)) {
      opts <- paste0("over(", x_var, ")")
      if (!is.null(facet_by)) opts <- paste0(opts, " by(", facet_by, ")")
      if (has_flip) opts <- paste0(opts, " horizontal")
      return(list(lines = paste0("barchart (mean) ", y_var, ", ", opts),
                  warnings = character(0)))
    }

    primary <- x_var %||% y_var
    if (is.null(primary))
      return(list(lines = "// ggplot geom_bar: no x aesthetic", warnings = character(0)))
    opts <- character(0)
    if (!is.null(fill_var)) opts <- c(opts, paste0("over(", fill_var, ")"))
    if (!is.null(facet_by)) opts <- c(opts, paste0("by(", facet_by, ")"))
    if (has_stack) opts <- c(opts, "stack")
    if (has_flip)  opts <- c(opts, "horizontal")
    cmd <- paste0("barchart (", stat_kw, ") ", primary)
    if (length(opts) > 0) cmd <- paste0(cmd, ", ", paste(opts, collapse = " "))
    return(list(lines = cmd, warnings = character(0)))
  }

  # ── boxplot ───────────────────────────────────────────────────────────────
  if (geom %in% c("geom_boxplot", "geom_violin")) {
    y_col <- y_var %||% x_var
    grp   <- if (!is.null(y_var) && !is.null(x_var)) x_var else fill_var
    if (is.null(y_col))
      return(list(lines = "// ggplot geom_boxplot: no y aesthetic", warnings = character(0)))
    opts <- character(0)
    if (!is.null(grp)) opts <- c(opts, paste0("over(", grp, ")"))
    if (has_flip)      opts <- c(opts, "horizontal")
    cmd <- paste0("boxplot ", y_col)
    if (length(opts) > 0) cmd <- paste0(cmd, ", ", paste(opts, collapse = " "))
    return(list(lines = cmd, warnings = character(0)))
  }

  # ── scatter / point → hexbin ──────────────────────────────────────────────
  if (geom %in% c("geom_point", "geom_jitter", "geom_hex", "geom_bin2d")) {
    if (is.null(x_var) || is.null(y_var))
      return(list(lines = "// ggplot geom_point: need both x and y aesthetics",
                  warnings = character(0)))
    return(list(lines = paste0("hexbin ", x_var, " ", y_var), warnings = character(0)))
  }

  # ── line / smooth → no direct equivalent ─────────────────────────────────
  if (geom %in% c("geom_line", "geom_smooth", "geom_path"))
    return(list(lines = paste0("// ggplot ", geom, ": no direct microdata equivalent"),
                warnings = character(0)))

  list(lines = paste0("// ggplot ", geom, ": no microdata equivalent"), warnings = character(0))
}

# ── plots / tabulations ───────────────────────────────────────────────────────

handle_table <- function(args, df_name) {
  cols <- sapply(args, function(a) {
    col_from_node(a, df_name) %||% (if (is.name(a)) as.character(a) else deparse(a))
  })
  list(lines = paste0("tabulate ", paste(cols, collapse = " ")), warnings = character(0))
}

handle_hist <- function(args, df_name) {
  col <- col_from_node(args[[1]], df_name) %||%
         (if (is.name(args[[1]])) as.character(args[[1]]) else NULL)
  if (is.null(col)) return(list(lines = "// hist: could not determine column", warnings = character(0)))
  list(lines = paste0("histogram ", col), warnings = character(0))
}

handle_boxplot <- function(args, df_name) {
  node <- args[[1]]
  if (is.call(node) && as.character(node[[1]]) == "~") {
    col   <- col_from_node(node[[2]], df_name) %||% as.character(node[[2]])
    grp   <- col_from_node(node[[3]], df_name) %||% as.character(node[[3]])
    return(list(lines = paste0("boxplot ", col, ", by(", grp, ")"), warnings = character(0)))
  }
  col <- col_from_node(node, df_name) %||% (if (is.name(node)) as.character(node) else NULL)
  if (is.null(col)) return(list(lines = "// boxplot: could not determine column", warnings = character(0)))
  list(lines = paste0("boxplot ", col), warnings = character(0))
}

handle_barplot <- function(args, df_name)
  list(lines = "// barplot → use barchart command in microdata", warnings = character(0))

handle_pie <- function(args, df_name) {
  node <- args[[1]]
  # pie(table(df$var)) → piechart var
  if (is.call(node) && as.character(node[[1]]) == "table") {
    targs <- as.list(node)[-1]
    if (length(targs) >= 1) {
      col <- col_from_node(targs[[1]], df_name) %||%
             (if (is.name(targs[[1]])) as.character(targs[[1]]) else NULL)
      if (!is.null(col)) return(list(lines = paste0("piechart ", col), warnings = character(0)))
    }
  }
  col <- col_from_node(node, df_name) %||% (if (is.name(node)) as.character(node) else NULL)
  if (!is.null(col)) return(list(lines = paste0("piechart ", col), warnings = character(0)))
  list(lines = "// pie: could not determine variable", warnings = character(0))
}

handle_summary <- function(args, df_name)
  list(lines = "summarize", warnings = character(0))

handle_normaltest <- function(args, df_name) {
  x_node <- args[[1]]
  col <- col_from_node(x_node, df_name) %||%
         (if (is.name(x_node)) as.character(x_node) else NULL)
  if (!is.null(col))
    return(list(lines = paste0("normaltest ", col), warnings = character(0)))
  list(lines = "// normaltest: could not determine variable", warnings = character(0))
}

handle_chisq_test <- function(args, df_name) {
  x_node <- args[[1]]
  # chisq.test(table(df$x, df$y))
  if (is.call(x_node) && as.character(x_node[[1]]) == "table") {
    targs <- as.list(x_node)[-1]
    cols  <- sapply(targs, function(a)
      col_from_node(a, df_name) %||% (if (is.name(a)) as.character(a) else NULL))
    cols  <- cols[!sapply(cols, is.null)]
    if (length(cols) >= 2)
      return(list(lines = paste0("tabulate ", paste(cols, collapse = " "), ", chi2"),
                  warnings = character(0)))
  }
  # chisq.test(df$x, df$y)
  if (length(args) >= 2) {
    x <- col_from_node(args[[1]], df_name) %||%
         (if (is.name(args[[1]])) as.character(args[[1]]) else NULL)
    y <- col_from_node(args[[2]], df_name) %||%
         (if (is.name(args[[2]])) as.character(args[[2]]) else NULL)
    if (!is.null(x) && !is.null(y))
      return(list(lines = paste0("tabulate ", x, " ", y, ", chi2"),
                  warnings = character(0)))
  }
  list(lines = "// chisq.test: could not determine variables", warnings = character(0))
}

# ── statistical tests ─────────────────────────────────────────────────────────

handle_cor <- function(args, df_name) {
  # cor(df[, c("x","y")]) or cor(df$x, df$y)
  if (length(args) >= 2) {
    y_node <- args[["y"]] %||% args[[2]]
    if (!is.null(y_node) && !is.logical(y_node)) {   # logical = use= arg, not y
      x <- col_from_node(args[[1]], df_name) %||%
           (if (is.name(args[[1]])) as.character(args[[1]]) else NULL)
      y <- col_from_node(y_node, df_name) %||%
           (if (is.name(y_node)) as.character(y_node) else NULL)
      if (!is.null(x) && !is.null(y))
        return(list(lines = paste0("correlate ", x, " ", y), warnings = character(0)))
    }
  }
  cols <- .extract_col_vector(args[[1]], df_name)
  if (!is.null(cols))
    return(list(lines = paste0("correlate ", paste(cols, collapse = " ")), warnings = character(0)))
  list(lines = "// cor: could not determine variables", warnings = character(0))
}

handle_aov <- function(args, df_name) {
  f_node <- args[["formula"]] %||% args[[1]]
  if (is.null(f_node)) return(NULL)
  parts <- .parse_formula(f_node, df_name)
  if (is.null(parts)) return(list(lines = "// aov: could not parse formula", warnings = character(0)))
  list(
    lines    = c(parts$preamble, paste0("anova ", parts$lhs, " ", paste(parts$rhs, collapse = " "))),
    warnings = parts$warnings
  )
}

handle_t_test <- function(args, df_name) {
  x_node <- args[[1]]
  fn_x   <- if (is.call(x_node)) as.character(x_node[[1]]) else ""

  # t.test(income ~ sex, data=df) — formula form
  if (fn_x == "~") {
    x_col <- col_from_node(x_node[[2]], df_name) %||%
             (if (is.name(x_node[[2]])) as.character(x_node[[2]]) else NULL)
    g_col <- col_from_node(x_node[[3]], df_name) %||%
             (if (is.name(x_node[[3]])) as.character(x_node[[3]]) else NULL)
    if (!is.null(x_col) && !is.null(g_col))
      return(list(lines = paste0("ci ", x_col, ", by(", g_col, ")"), warnings = character(0)))
  }

  x_col <- col_from_node(x_node, df_name) %||%
           (if (is.name(x_node)) as.character(x_node) else NULL)

  # t.test(df$x, df$y) — two-sample
  y_node <- args[["y"]] %||% args[[2]]
  if (!is.null(y_node)) {
    y_col <- col_from_node(y_node, df_name) %||%
             (if (is.name(y_node)) as.character(y_node) else NULL)
    if (!is.null(x_col) && !is.null(y_col))
      return(list(lines = paste0("ci ", x_col, " ", y_col), warnings = character(0)))
  }

  if (!is.null(x_col))
    return(list(lines = paste0("ci ", x_col), warnings = character(0)))
  list(lines = "// t.test: could not determine variables", warnings = character(0))
}

# ── advanced regression ───────────────────────────────────────────────────────

handle_glm_nb <- function(args, df_name) {
  f_node <- args[["formula"]] %||% args[[1]]
  if (is.null(f_node)) return(NULL)
  parts <- .parse_formula(f_node, df_name)
  if (is.null(parts)) return(list(lines = "// glm.nb: could not parse formula", warnings = character(0)))
  list(
    lines    = c(parts$preamble, paste0("negative-binomial ", parts$lhs, " ",
                                        paste(parts$rhs, collapse = " "))),
    warnings = parts$warnings
  )
}

handle_multinom <- function(args, df_name) {
  f_node <- args[["formula"]] %||% args[[1]]
  if (is.null(f_node)) return(NULL)
  parts <- .parse_formula(f_node, df_name)
  if (is.null(parts)) return(list(lines = "// multinom: could not parse formula", warnings = character(0)))
  list(
    lines    = c(parts$preamble, paste0("mlogit ", parts$lhs, " ", paste(parts$rhs, collapse = " "))),
    warnings = parts$warnings
  )
}

handle_ivreg <- function(args, df_name) {
  f_node <- args[["formula"]] %||% args[[1]]
  if (is.null(f_node)) return(NULL)
  if (!is.call(f_node) || as.character(f_node[[1]]) != "~")
    return(list(lines = "// ivreg: could not parse formula", warnings = character(0)))
  lhs      <- as.character(f_node[[2]])
  rhs_node <- f_node[[3]]

  if (is.call(rhs_node) && as.character(rhs_node[[1]]) == "|") {
    regressors   <- .formula_terms(rhs_node[[2]])
    all_instru   <- .formula_terms(rhs_node[[3]])
    instru_only  <- setdiff(all_instru, regressors)
    cmd <- paste0("ivregress ", lhs, " ", paste(regressors, collapse = " "))
    if (length(instru_only) > 0)
      cmd <- paste0(cmd, ", iv(", paste(instru_only, collapse = " "), ")")
  } else {
    terms <- .formula_terms(rhs_node)
    cmd   <- paste0("ivregress ", lhs, " ", paste(terms, collapse = " "))
  }
  list(lines = cmd, warnings = character(0))
}

# ── survival analysis ─────────────────────────────────────────────────────────

.parse_surv_formula <- function(f_node) {
  # Returns list(time, event, groups) or NULL
  if (!is.call(f_node) || as.character(f_node[[1]]) != "~") return(NULL)
  surv_node <- f_node[[2]]
  if (!is.call(surv_node) ||
      sub("^.*::", "", as.character(surv_node[[1]])) != "Surv") return(NULL)
  surv_args <- as.list(surv_node)[-1]
  if (length(surv_args) < 2) return(NULL)
  rhs_node  <- f_node[[3]]
  groups    <- .formula_terms(rhs_node)
  groups    <- groups[groups != "1"]
  list(
    time   = as.character(surv_args[[1]]),
    event  = as.character(surv_args[[2]]),
    groups = groups
  )
}

handle_survfit <- function(args, df_name) {
  f_node <- args[["formula"]] %||% args[[1]]
  if (is.null(f_node)) return(NULL)
  s <- .parse_surv_formula(f_node)
  if (is.null(s))
    return(list(lines = "// survfit: expected Surv(time, event) ~ group formula",
                warnings = character(0)))
  by_str <- if (length(s$groups) > 0)
    paste0(", by(", paste(s$groups, collapse = " "), ")")
  else ""
  list(lines = paste0("kaplan-meier ", s$time, " ", s$event, by_str), warnings = character(0))
}

handle_coxph <- function(args, df_name) {
  f_node <- args[["formula"]] %||% args[[1]]
  if (is.null(f_node)) return(NULL)
  s <- .parse_surv_formula(f_node)
  if (is.null(s))
    return(list(lines = "// coxph: expected Surv(time, event) ~ x formula",
                warnings = character(0)))
  if (length(s$groups) == 0)
    return(list(lines = "// coxph: no predictors found", warnings = character(0)))
  list(lines = paste0("cox ", s$time, " ", s$event, " ", paste(s$groups, collapse = " ")),
       warnings = character(0))
}

# ── panel / RDD / oaxaca regression ──────────────────────────────────────────

handle_rdrobust <- function(args, df_name) {
  y_node <- args[["y"]] %||% args[[1]]
  x_node <- args[["x"]] %||% (if (length(args) >= 2) args[[2]] else NULL)
  if (is.null(y_node) || is.null(x_node)) return(NULL)
  y <- col_from_node(y_node, df_name) %||%
       (if (is.name(y_node)) as.character(y_node) else NULL)
  x <- col_from_node(x_node, df_name) %||%
       (if (is.name(x_node)) as.character(x_node) else NULL)
  if (is.null(y) || is.null(x))
    return(list(lines = "// rdrobust: could not determine variables", warnings = character(0)))
  c_node <- args[["c"]] %||% args[["cutoff"]]
  opts   <- character(0)
  if (!is.null(c_node) && is.numeric(c_node) && c_node != 0)
    opts <- c(opts, paste0("cutoff(", c_node, ")"))
  cmd <- paste0("rdd ", y, " ", x)
  if (length(opts)) cmd <- paste0(cmd, ", ", paste(opts, collapse = " "))
  list(lines = cmd, warnings = character(0))
}

handle_plm <- function(args, df_name) {
  f_node     <- args[["formula"]] %||% args[[1]]
  model_node <- args[["model"]]
  if (is.null(f_node)) return(NULL)
  model_str <- if (!is.null(model_node) && is.character(model_node)) model_node else "within"
  opt <- switch(model_str,
    within  = "fe", random = "re", between = "be", pooling = "pooled", "fe")
  parts <- .parse_formula(f_node, df_name)
  if (is.null(parts))
    return(list(lines = "// plm: could not parse formula", warnings = character(0)))
  cmd <- paste0("regress-panel ", parts$lhs, " ", paste(parts$rhs, collapse = " "), ", ", opt)
  list(lines = c(parts$preamble, cmd), warnings = parts$warnings)
}

handle_lmer <- function(args, df_name) {
  f_node <- args[["formula"]] %||% args[[1]]
  if (is.null(f_node)) return(NULL)
  if (!is.call(f_node) || as.character(f_node[[1]]) != "~")
    return(list(lines = "// lmer: could not parse formula", warnings = character(0)))
  lhs <- as.character(f_node[[2]])
  fixed_terms <- character(0)
  groups      <- character(0)

  .walk <- function(node) {
    if (is.name(node)) { fixed_terms <<- c(fixed_terms, as.character(node)); return() }
    if (!is.call(node)) return()
    fn2 <- as.character(node[[1]])
    if (fn2 == "+")  { .walk(node[[2]]); .walk(node[[3]]); return() }
    if (fn2 == "(") {
      inner <- node[[2]]
      if (is.call(inner) && as.character(inner[[1]]) == "|") {
        groups <<- c(groups, as.character(inner[[3]])); return()
      }
    }
    fixed_terms <<- c(fixed_terms, deparse(node))
  }
  .walk(f_node[[3]])
  fixed_terms <- setdiff(fixed_terms, c("1", "0", "-1"))

  if (length(groups) == 0)
    return(list(
      lines    = paste0("regress ", lhs, " ", paste(fixed_terms, collapse = " ")),
      warnings = "// lmer: no random effect found, using regress"))
  cmd <- paste0("regress-mml ", lhs, " ", paste(fixed_terms, collapse = " "),
                " by ", paste(groups, collapse = " "))
  list(lines = cmd, warnings = character(0))
}

handle_oaxaca <- function(args, df_name) {
  f_node <- args[["formula"]] %||% args[[1]]
  if (is.null(f_node)) return(NULL)
  if (!is.call(f_node) || as.character(f_node[[1]]) != "~")
    return(list(lines = "// oaxaca: could not parse formula", warnings = character(0)))
  lhs      <- as.character(f_node[[2]])
  rhs_node <- f_node[[3]]

  # y ~ x | group_var  (group on RHS after |)
  if (is.call(rhs_node) && as.character(rhs_node[[1]]) == "|") {
    regs  <- setdiff(.formula_terms(rhs_node[[2]]), c("1", "0"))
    grp   <- as.character(rhs_node[[3]])
    return(list(lines = paste0("oaxaca ", lhs, " ", paste(regs, collapse = " "),
                               " by ", grp), warnings = character(0)))
  }
  # by= argument
  by_node <- args[["by"]]
  by_str  <- if (!is.null(by_node) && is.character(by_node)) by_node
             else if (!is.null(by_node) && is.name(by_node)) as.character(by_node)
             else NULL
  if (is.null(by_str))
    return(list(lines = "// oaxaca: could not determine by variable", warnings = character(0)))
  regs <- setdiff(.formula_terms(rhs_node), c("1", "0"))
  list(lines = paste0("oaxaca ", lhs, " ", paste(regs, collapse = " "), " by ", by_str),
       warnings = character(0))
}

# ── joins / merge ─────────────────────────────────────────────────────────────

# microdata merge syntax: merge var-list into dataset [on variable]
# The SOURCE dataset (y_df) must be active when merge runs.
# We emit `use y_df` first so the translator output is self-contained.
# The variable list is unknown at translation time → placeholder + warning.
.handle_join_base <- function(args, df_name) {
  y_node <- args[[1]]
  y_df   <- if (is.name(y_node)) as.character(y_node) else NULL
  if (is.null(y_df))
    return(list(lines = "// join: could not determine source dataset", warnings = character(0)))

  by_arg <- args[["by"]]
  by     <- .parse_by_cols(by_arg)
  warns  <- if (!is.null(by$warning)) by$warning else character(0)

  # microdata `on` accepts a single linking variable
  on_clause <- ""
  if (!is.null(by$cols) && length(by$cols) >= 1) {
    if (length(by$cols) > 1)
      warns <- c(warns, paste0("// merge: microdata 'on' takes one variable; using '",
                               by$cols[1], "' — verify manually"))
    on_clause <- paste0(" on ", by$cols[1])
  }

  var_placeholder <- paste0("<vars_from_", y_df, ">")
  lines <- c(
    paste0("use ", y_df),
    paste0("merge ", var_placeholder, " into ", df_name, on_clause),
    paste0("// Replace ", var_placeholder, " with the variable names to bring in from ", y_df)
  )
  list(lines = lines, warnings = warns)
}

handle_left_join <- function(args, df_name, group_by = NULL) .handle_join_base(args, df_name)

handle_right_join <- function(args, df_name, group_by = NULL) {
  # right_join keeps all rows from df2 — swap source/target perspective
  y_node <- args[[1]]
  y_df   <- if (is.name(y_node)) as.character(y_node) else NULL
  if (is.null(y_df))
    return(list(lines = "// right_join: could not determine source dataset", warnings = character(0)))
  by_arg <- args[["by"]]
  by     <- .parse_by_cols(by_arg)
  warns  <- c(if (!is.null(by$warning)) by$warning else character(0),
              paste0("// right_join: consider merging from ", df_name, " into ", y_df, " instead"))
  on_clause <- ""
  if (!is.null(by$cols) && length(by$cols) >= 1)
    on_clause <- paste0(" on ", by$cols[1])
  var_placeholder <- paste0("<vars_from_", df_name, ">")
  list(
    lines = c(
      paste0("use ", df_name),
      paste0("merge ", var_placeholder, " into ", y_df, on_clause),
      paste0("// Replace ", var_placeholder, " with the variable names to bring in from ", df_name)
    ),
    warnings = warns
  )
}

handle_inner_join <- function(args, df_name, group_by = NULL) {
  r <- .handle_join_base(args, df_name)
  r$warnings <- c(r$warnings,
    "// inner_join: microdata merge keeps all target rows; no built-in drop of unmatched rows")
  r
}

handle_full_join <- function(args, df_name, group_by = NULL) {
  r <- .handle_join_base(args, df_name)
  r$warnings <- c(r$warnings,
    "// full_join: microdata merge is one-directional; rows in source not in target are not added")
  r
}

handle_anti_join <- function(args, df_name, group_by = NULL) {
  y_node <- args[[1]]
  y_df   <- if (is.name(y_node)) as.character(y_node) else "?"
  list(lines = paste0("// anti_join with ", y_df, ": no direct microdata equivalent"),
       warnings = character(0))
}

handle_semi_join <- function(args, df_name, group_by = NULL) {
  y_node <- args[[1]]
  y_df   <- if (is.name(y_node)) as.character(y_node) else "?"
  list(lines = paste0("// semi_join with ", y_df, ": no direct microdata equivalent"),
       warnings = character(0))
}

# ── reshape ───────────────────────────────────────────────────────────────────

handle_pivot_longer <- function(args, df_name, group_by = NULL) {
  cols_arg   <- args[["cols"]]
  names_to   <- args[["names_to"]]
  values_to  <- args[["values_to"]]

  if (is.null(cols_arg))
    return(list(lines = "// pivot_longer: cols= argument required", warnings = character(0)))
  cols <- .extract_col_vector(cols_arg, df_name)
  if (is.null(cols))
    return(list(lines = "// pivot_longer: could not parse cols= argument", warnings = character(0)))

  year_var  <- if (!is.null(names_to)  && is.character(names_to))  names_to  else "year"
  value_var <- if (!is.null(values_to) && is.character(values_to)) values_to else "value"

  list(
    lines    = paste0("reshape-to-panel ", paste(cols, collapse = " "),
                      ", year(", year_var, ") value(", value_var, ")"),
    warnings = character(0)
  )
}

handle_pivot_wider <- function(args, df_name, group_by = NULL) {
  names_from  <- args[["names_from"]]
  values_from <- args[["values_from"]]

  .name <- function(n) {
    if (is.null(n)) NULL
    else if (is.name(n)) as.character(n)
    else if (is.character(n)) n
    else NULL
  }
  year_var  <- .name(names_from)
  value_var <- .name(values_from)

  if (is.null(value_var))
    return(list(lines = "// pivot_wider: values_from= argument required", warnings = character(0)))
  cmd <- paste0("reshape-from-panel ", value_var)
  if (!is.null(year_var)) cmd <- paste0(cmd, ", year(", year_var, ")")
  list(lines = cmd, warnings = character(0))
}

# ── sampling ──────────────────────────────────────────────────────────────────

handle_sample_n <- function(args, df_name, group_by = NULL) {
  n_node <- args[["n"]] %||% (if (length(args) >= 1) args[[1]] else NULL)
  if (is.null(n_node))
    return(list(lines = "// sample_n: missing n argument", warnings = character(0)))
  list(lines = paste0("sample ", as.character(n_node)), warnings = character(0))
}

handle_sample_frac <- function(args, df_name, group_by = NULL) {
  s_node <- args[["size"]] %||% (if (length(args) >= 1) args[[1]] else NULL)
  if (is.null(s_node))
    return(list(lines = "// sample_frac: missing size argument", warnings = character(0)))
  pct <- tryCatch(as.numeric(s_node) * 100, error = function(e) NULL)
  if (!is.null(pct))
    return(list(lines = paste0("sample ", pct), warnings = character(0)))
  list(lines = "// sample_frac: could not compute percentage", warnings = character(0))
}

# ── count ─────────────────────────────────────────────────────────────────────

handle_count <- function(args, df_name, group_by = NULL) {
  cols <- sapply(args, function(a) {
    col_from_node(a, df_name) %||% (if (is.name(a)) as.character(a) else NULL)
  })
  cols <- cols[!sapply(cols, is.null)]
  if (length(cols) > 0)
    return(list(lines = paste0("tabulate ", paste(cols, collapse = " ")), warnings = character(0)))
  list(lines = "// count: could not determine columns", warnings = character(0))
}

# ── dispatch table ────────────────────────────────────────────────────────────

DPLYR_DISPATCH <- list(
  filter    = handle_filter,
  mutate    = handle_mutate,
  transmute = handle_mutate,
  select    = handle_select,
  rename    = handle_rename,
  summarise = handle_summarise,
  summarize = handle_summarise,
  arrange   = handle_arrange,
  drop_na   = handle_drop_na,
  distinct  = handle_distinct,
  slice_head = handle_slice_head,
  slice_max  = handle_slice_head,
  slice_min  = handle_slice_head,
  # tidy helpers
  count        = handle_count,
  sample_n     = handle_sample_n,
  sample_frac  = handle_sample_frac,
  # reshape
  pivot_longer = handle_pivot_longer,
  pivot_wider  = handle_pivot_wider,
  # joins
  left_join    = handle_left_join,
  right_join   = handle_right_join,
  inner_join   = handle_inner_join,
  full_join    = handle_full_join,
  anti_join    = handle_anti_join,
  semi_join    = handle_semi_join
)

dispatch_dplyr <- function(fn_name, args, df_name, group_by = NULL) {
  handler <- DPLYR_DISPATCH[[fn_name]]
  if (!is.null(handler)) return(handler(args, df_name, group_by))
  NULL
}

STANDALONE_DISPATCH <- list(
  # base regression + model fitting
  lm          = function(args, df_name) handle_lm(args, df_name),
  glm         = function(args, df_name) handle_glm(args, df_name),
  aov         = function(args, df_name) handle_aov(args, df_name),
  # advanced regression (package-based)
  glm.nb      = function(args, df_name) handle_glm_nb(args, df_name),
  multinom    = function(args, df_name) handle_multinom(args, df_name),
  ivreg       = function(args, df_name) handle_ivreg(args, df_name),
  # survival
  coxph       = function(args, df_name) handle_coxph(args, df_name),
  survfit     = function(args, df_name) handle_survfit(args, df_name),
  # statistical tests
  cor         = function(args, df_name) handle_cor(args, df_name),
  t.test      = function(args, df_name) handle_t_test(args, df_name),
  shapiro.test  = function(args, df_name) handle_normaltest(args, df_name),
  chisq.test    = function(args, df_name) handle_chisq_test(args, df_name),
  # panel / RDD / oaxaca
  plm           = function(args, df_name) handle_plm(args, df_name),
  lmer          = function(args, df_name) handle_lmer(args, df_name),
  rdrobust      = function(args, df_name) handle_rdrobust(args, df_name),
  oaxaca        = function(args, df_name) handle_oaxaca(args, df_name),
  # plots
  table       = function(args, df_name) handle_table(args, df_name),
  hist        = function(args, df_name) handle_hist(args, df_name),
  boxplot     = function(args, df_name) handle_boxplot(args, df_name),
  barplot     = function(args, df_name) handle_barplot(args, df_name),
  pie         = function(args, df_name) handle_pie(args, df_name),
  summary     = function(args, df_name) handle_summary(args, df_name),
  # silenced
  print       = function(args, df_name) list(lines = character(0), warnings = character(0)),
  cat         = function(args, df_name) list(lines = character(0), warnings = character(0)),
  message     = function(args, df_name) list(lines = character(0), warnings = character(0))
)

dispatch_standalone <- function(fn_name, args, df_name) {
  fn_clean <- sub("^.*::", "", fn_name)
  handler  <- STANDALONE_DISPATCH[[fn_clean]]
  if (!is.null(handler)) return(handler(args, df_name))
  NULL
}
