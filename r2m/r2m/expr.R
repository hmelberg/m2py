# expr.R — Translates R AST expression nodes to microdata.no expression strings.
#
# col_from_node(node, df_name)  → character column name or NULL
# translate_expr(node, df_name) → microdata expression string or NULL

`%||%` <- function(a, b) if (!is.null(a) && length(a) > 0) a else b

# ── distribution-function helpers ─────────────────────────────────────────────
# Returns TRUE when lower.tail is TRUE (the default) or absent.
.lower_tail <- function(args) {
  lt <- args[["lower.tail"]]
  if (is.null(lt)) return(TRUE)
  if (is.logical(lt)) return(isTRUE(lt))
  if (is.name(lt)) return(as.character(lt) != "FALSE")
  TRUE
}
# Returns translated ncp expression string, or NULL when absent.
.ncp_expr <- function(args, df_name) {
  nd <- args[["ncp"]]
  if (is.null(nd)) return(NULL)
  translate_expr(nd, df_name)
}
# Convenience: build "fn(a, b, …)" string.
.mk <- function(fn, ...) paste0(fn, "(", paste(c(...), collapse = ", "), ")")

# Microdata-native functions that pass through unchanged
MICRODATA_FUNCS <- c(
  "ln", "log10", "sqrt", "exp", "abs", "ceil", "floor", "int", "round",
  "cos", "sin", "tan", "acos", "asin", "atan", "comb", "lnfactorial",
  "date", "year", "month", "day", "week", "halfyear", "quarter", "dow", "doy",
  "normal", "normalden",
  "chi2", "chi2den", "chi2tail", "invchi2", "invchi2tail",
  "t", "tden", "ttail", "invt", "invttail",
  "F", "Fden", "Ftail", "invF", "invFtail",
  "binomial", "binomialp", "binomialtail",
  "betaden", "ibeta", "ibetatail", "invibeta", "invibetatail",
  "nF", "nFden", "nFtail", "nchi2", "nchi2den", "nchi2tail",
  "nt", "ntden", "nttail", "invnttail",
  "length", "string", "lower", "upper", "substr",
  "trim", "ltrim", "rtrim", "startswith", "endswith",
  "inlist", "inrange", "sysmiss",
  "rowmax", "rowmin", "rowmean", "rowmedian", "rowtotal",
  "rowstd", "rowmissing", "rowvalid", "rowconcat",
  "quantile", "to_int", "to_str", "logit"
)

#' Extract column name from df$col, df[["col"]], or df["col"] node.
#' Returns character or NULL.
col_from_node <- function(node, df_name = "df") {
  if (!is.call(node)) return(NULL)
  fn <- as.character(node[[1]])
  if (fn == "$") {
    if (is.name(node[[2]]) && as.character(node[[2]]) == df_name) {
      return(as.character(node[[3]]))  # symbol on RHS of $ is the column name
    }
  } else if (fn %in% c("[[", "[")) {
    if (length(node) >= 3 && is.name(node[[2]]) && as.character(node[[2]]) == df_name) {
      idx <- node[[3]]
      if (is.character(idx)) return(idx)
      if (is.atomic(idx))    return(as.character(idx))
    }
  }
  NULL
}

#' Translate an R expression AST node to a microdata expression string.
#' Returns character string or NULL when not translatable.
translate_expr <- function(node, df_name = "df") {
  if (is.null(node)) return(NULL)

  # --- literals ---
  if (is.character(node)) return(paste0("'", node, "'"))
  if (is.logical(node))   return(if (isTRUE(node)) "1" else "0")
  if (is.numeric(node))   return(as.character(node))

  # --- bare names ---
  if (is.name(node)) {
    n <- as.character(node)
    if (n == df_name)                            return(NULL)
    if (n %in% c("TRUE",  "T"))                  return("1")
    if (n %in% c("FALSE", "F"))                  return("0")
    if (n %in% c("NA", "NaN", "Inf",
                 "NA_real_", "NA_integer_",
                 "NA_character_", "NA_complex_")) return(".")
    if (n == "NULL")                              return(NULL)
    if (n == "pi")                               return("pi()")
    return(n)   # column name or let-binding
  }

  if (!is.call(node)) return(NULL)
  fn   <- as.character(node[[1]])
  args <- as.list(node)[-1]  # named list of arguments

  # --- df$col / df[["col"]] → column name ---
  col <- col_from_node(node, df_name)
  if (!is.null(col)) return(col)

  # --- arithmetic ---
  if (fn %in% c("+", "-", "*", "/", "^", "%%", "%/%")) {
    if (length(args) == 1) {                # unary +/-
      v <- translate_expr(args[[1]], df_name)
      if (is.null(v)) return(NULL)
      return(if (fn == "-") paste0("(-", v, ")") else v)
    }
    op <- switch(fn, "^" = "**", "%%" = "%", "%/%" = "//", fn)
    l <- translate_expr(args[[1]], df_name)
    r <- translate_expr(args[[2]], df_name)
    if (is.null(l) || is.null(r)) return(NULL)
    return(paste0("(", l, " ", op, " ", r, ")"))
  }

  # --- comparisons ---
  if (fn %in% c("==", "!=", "<", "<=", ">", ">=")) {
    l <- translate_expr(args[[1]], df_name)
    r <- translate_expr(args[[2]], df_name)
    if (is.null(l) || is.null(r)) return(NULL)
    return(paste0(l, " ", fn, " ", r))
  }

  # --- boolean ---
  if (fn %in% c("&", "&&")) {
    l <- translate_expr(args[[1]], df_name)
    r <- translate_expr(args[[2]], df_name)
    if (is.null(l) || is.null(r)) return(NULL)
    return(paste0("(", l, ") & (", r, ")"))
  }
  if (fn %in% c("|", "||")) {
    l <- translate_expr(args[[1]], df_name)
    r <- translate_expr(args[[2]], df_name)
    if (is.null(l) || is.null(r)) return(NULL)
    return(paste0("(", l, ") | (", r, ")"))
  }
  if (fn == "!") {
    inner <- args[[1]]
    # !is.na(x) → (!sysmiss(x))
    if (is.call(inner) && as.character(inner[[1]]) %in% c("is.na", "is.null")) {
      v <- translate_expr(as.list(inner)[-1][[1]], df_name)
      if (!is.null(v)) return(paste0("(!sysmiss(", v, "))"))
    }
    v <- translate_expr(inner, df_name)
    if (is.null(v)) return(NULL)
    return(paste0("!(", v, ")"))
  }

  # --- %in% → inlist ---
  if (fn == "%in%") {
    col <- translate_expr(args[[1]], df_name)
    vals_node <- args[[2]]
    if (!is.null(col) && is.call(vals_node) && as.character(vals_node[[1]]) == "c") {
      vals <- sapply(as.list(vals_node)[-1], translate_expr, df_name = df_name)
      if (!any(sapply(vals, is.null)))
        return(paste0("inlist(", col, ", ", paste(vals, collapse = ", "), ")"))
    }
    return(NULL)
  }

  # --- dplyr::between → inrange ---
  if (fn %in% c("between", "dplyr::between") && length(args) == 3) {
    x  <- translate_expr(args[[1]], df_name)
    lo <- translate_expr(args[[2]], df_name)
    hi <- translate_expr(args[[3]], df_name)
    if (!is.null(x) && !is.null(lo) && !is.null(hi))
      return(paste0("inrange(", x, ", ", lo, ", ", hi, ")"))
  }

  # --- NA tests ---
  if (fn %in% c("is.na", "is.null")) {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(paste0("sysmiss(", v, ")"))
  }

  # --- math ---
  if (fn == "log") {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) {
      base_node <- args[["base"]] %||% (if (length(args) >= 2) args[[2]] else NULL)
      if (!is.null(base_node)) {
        b <- translate_expr(base_node, df_name)
        if (!is.null(b) && b == "10") return(paste0("log10(", v, ")"))
        return(NULL)  # log with other base has no microdata equivalent
      }
      return(paste0("ln(", v, ")"))
    }
  }
  if (fn == "log10") {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(paste0("log10(", v, ")"))
  }
  if (fn == "exp") {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(paste0("exp(", v, ")"))
  }
  if (fn == "sqrt") {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(paste0("sqrt(", v, ")"))
  }
  if (fn == "abs") {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(paste0("abs(", v, ")"))
  }
  if (fn == "ceiling") {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(paste0("ceil(", v, ")"))
  }
  if (fn == "floor") {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(paste0("floor(", v, ")"))
  }
  if (fn == "round") {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) {
      d_node <- args[["digits"]] %||% (if (length(args) >= 2) args[[2]] else NULL)
      if (!is.null(d_node)) {
        d <- translate_expr(d_node, df_name)
        if (!is.null(d)) return(paste0("round(", v, ", ", d, ")"))
      }
      return(paste0("round(", v, ")"))
    }
  }
  if (fn %in% c("trunc", "as.integer")) {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(paste0("int(", v, ")"))
  }
  if (fn == "as.character") {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(paste0("string(", v, ")"))
  }
  if (fn %in% c("cos", "sin", "tan", "acos", "asin", "atan")) {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(paste0(fn, "(", v, ")"))
  }

  # --- string functions ---
  if (fn == "toupper") {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(paste0("upper(", v, ")"))
  }
  if (fn == "tolower") {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(paste0("lower(", v, ")"))
  }
  if (fn == "nchar") {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(paste0("length(", v, ")"))
  }
  if (fn %in% c("trimws", "str_trim")) {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) {
      which_arg <- args[["which"]] %||% (if (length(args) >= 2) args[[2]] else NULL)
      w <- if (!is.null(which_arg) && is.character(which_arg)) which_arg else "both"
      return(switch(w, left = .mk("ltrim", v), right = .mk("rtrim", v), .mk("trim", v)))
    }
  }
  if (fn %in% c("startsWith", "str_starts")) {
    v <- translate_expr(args[[1]], df_name)
    p <- translate_expr(args[[2]], df_name)
    if (!is.null(v) && !is.null(p)) return(paste0("startswith(", v, ", ", p, ")"))
  }
  if (fn %in% c("endsWith", "str_ends")) {
    v <- translate_expr(args[[1]], df_name)
    p <- translate_expr(args[[2]], df_name)
    if (!is.null(v) && !is.null(p)) return(paste0("endswith(", v, ", ", p, ")"))
  }
  if (fn %in% c("substr", "substring")) {
    v     <- translate_expr(args[[1]], df_name)
    start <- translate_expr(args[[2]], df_name)
    stop_node <- args[["stop"]] %||% (if (length(args) >= 3) args[[3]] else NULL)
    if (!is.null(v) && !is.null(start)) {
      if (!is.null(stop_node)) {
        stop_val <- translate_expr(stop_node, df_name)
        # microdata substr(col, start, length); R substr uses stop (inclusive)
        len <- tryCatch(as.numeric(stop_val) - as.numeric(start) + 1, error = function(e) NULL)
        if (!is.null(len)) return(paste0("substr(", v, ", ", start, ", ", len, ")"))
      }
      return(paste0("substr(", v, ", ", start, ", .)"))
    }
  }
  if (fn %in% c("str_length", "str_count") && fn == "str_length") {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(paste0("length(", v, ")"))
  }
  if (fn == "str_to_upper") {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(paste0("upper(", v, ")"))
  }
  if (fn == "str_to_lower") {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(paste0("lower(", v, ")"))
  }
  if (fn == "str_sub") {
    v     <- translate_expr(args[[1]], df_name)
    start <- translate_expr(args[[2]], df_name)
    end_node <- args[["end"]] %||% (if (length(args) >= 3) args[[3]] else NULL)
    if (!is.null(v) && !is.null(start)) {
      if (!is.null(end_node)) {
        end_val <- translate_expr(end_node, df_name)
        len <- tryCatch(as.numeric(end_val) - as.numeric(start) + 1, error = function(e) NULL)
        if (!is.null(len)) return(paste0("substr(", v, ", ", start, ", ", len, ")"))
      }
      return(paste0("substr(", v, ", ", start, ", .)"))
    }
  }

  # --- date functions (lubridate / base) ---
  if (fn %in% c("year", "month", "day", "week", "quarter")) {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(paste0(fn, "(", v, ")"))
  }
  if (fn == "wday") {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(paste0("dow(", v, ")"))
  }
  if (fn == "yday") {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(paste0("doy(", v, ")"))
  }

  # --- probability: normal ---
  if (fn == "pnorm" && .lower_tail(args)) {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(.mk("normal", v))
  }
  if (fn == "dnorm") {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(.mk("normalden", v))
  }

  # --- probability: t-distribution ---
  if (fn %in% c("dt", "pt", "qt")) {
    x   <- translate_expr(args[[1]], df_name)
    vnd <- args[["df"]] %||% (if (length(args) >= 2) args[[2]] else NULL)
    if (!is.null(x) && !is.null(vnd)) {
      v   <- translate_expr(vnd, df_name)
      lt  <- .lower_tail(args)
      ncp <- .ncp_expr(args, df_name)
      if (!is.null(v)) {
        if (fn == "dt")
          return(.mk("tden", x, v))    # ntden has no ncp arg per docs; skip ncp
        if (fn == "pt" && !is.null(ncp))
          return(if (lt) .mk("nt", x, v, ncp) else .mk("nttail", x, v, ncp))
        if (fn == "pt")
          return(if (lt) .mk("t", x, v) else .mk("ttail", x, v))
        if (fn == "qt" && !is.null(ncp) && !lt)
          return(.mk("invnttail", x, v, ncp))
        if (fn == "qt")
          return(if (lt) .mk("invt", x, v) else .mk("invttail", x, v))
      }
    }
  }

  # --- probability: chi-squared ---
  if (fn %in% c("dchisq", "pchisq", "qchisq")) {
    x   <- translate_expr(args[[1]], df_name)
    vnd <- args[["df"]] %||% (if (length(args) >= 2) args[[2]] else NULL)
    if (!is.null(x) && !is.null(vnd)) {
      v   <- translate_expr(vnd, df_name)
      lt  <- .lower_tail(args)
      ncp <- .ncp_expr(args, df_name)
      if (!is.null(v)) {
        if (fn == "dchisq")
          return(if (!is.null(ncp)) .mk("nchi2den", x, v, ncp) else .mk("chi2den", x, v))
        if (fn == "pchisq" && !is.null(ncp))
          return(if (lt) .mk("nchi2", x, v, ncp) else .mk("nchi2tail", x, v, ncp))
        if (fn == "pchisq")
          return(if (lt) .mk("chi2", x, v) else .mk("chi2tail", x, v))
        if (fn == "qchisq")
          return(if (lt) .mk("invchi2", x, v) else .mk("invchi2tail", x, v))
      }
    }
  }

  # --- probability: F-distribution ---
  # Safe to translate pf/qf unconditionally; stats::df required for density
  # (bare "df" collides with the user's data-frame variable).
  if (fn %in% c("pf", "qf", "stats::df")) {
    x   <- translate_expr(args[[1]], df_name)
    v1n <- args[["df1"]] %||% (if (length(args) >= 2) args[[2]] else NULL)
    v2n <- args[["df2"]] %||% (if (length(args) >= 3) args[[3]] else NULL)
    if (!is.null(x) && !is.null(v1n) && !is.null(v2n)) {
      v1  <- translate_expr(v1n, df_name)
      v2  <- translate_expr(v2n, df_name)
      lt  <- .lower_tail(args)
      ncp <- .ncp_expr(args, df_name)
      if (!is.null(v1) && !is.null(v2)) {
        if (fn == "stats::df")
          return(if (!is.null(ncp)) .mk("nFden", x, v1, v2, ncp) else .mk("Fden", x, v1, v2))
        if (fn == "pf" && !is.null(ncp))
          return(if (lt) .mk("nF", x, v1, v2, ncp) else .mk("nFtail", x, v1, v2, ncp))
        if (fn == "pf")
          return(if (lt) .mk("F", x, v1, v2) else .mk("Ftail", x, v1, v2))
        if (fn == "qf")
          return(if (lt) .mk("invF", x, v1, v2) else .mk("invFtail", x, v1, v2))
      }
    }
  }

  # --- probability: beta distribution ---
  if (fn %in% c("dbeta", "pbeta", "qbeta")) {
    x   <- translate_expr(args[[1]], df_name)
    an  <- args[["shape1"]] %||% (if (length(args) >= 2) args[[2]] else NULL)
    bn  <- args[["shape2"]] %||% (if (length(args) >= 3) args[[3]] else NULL)
    if (!is.null(x) && !is.null(an) && !is.null(bn)) {
      a  <- translate_expr(an, df_name)
      b  <- translate_expr(bn, df_name)
      lt <- .lower_tail(args)
      if (!is.null(a) && !is.null(b)) {
        if (fn == "dbeta") return(.mk("betaden", x, a, b))
        if (fn == "pbeta") return(if (lt) .mk("ibeta", x, a, b) else .mk("ibetatail", x, a, b))
        if (fn == "qbeta") return(if (lt) .mk("invibeta", x, a, b) else .mk("invibetatail", x, a, b))
      }
    }
  }

  # --- probability: binomial ---
  if (fn %in% c("dbinom", "pbinom")) {
    x  <- translate_expr(args[[1]], df_name)
    sn <- args[["size"]] %||% (if (length(args) >= 2) args[[2]] else NULL)
    pn <- args[["prob"]] %||% (if (length(args) >= 3) args[[3]] else NULL)
    if (!is.null(x) && !is.null(sn) && !is.null(pn)) {
      s <- translate_expr(sn, df_name)
      p <- translate_expr(pn, df_name)
      if (!is.null(s) && !is.null(p)) {
        if (fn == "dbinom") return(.mk("binomialp", x, s, p))
        if (fn == "pbinom") return(.mk("binomial",  x, s, p))
      }
    }
  }

  # --- combinatorics ---
  if (fn == "choose" && length(args) >= 2) {
    n <- translate_expr(args[[1]], df_name)
    k <- translate_expr(args[[2]], df_name)
    if (!is.null(n) && !is.null(k)) return(.mk("comb", n, k))
  }
  if (fn == "lfactorial") {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(.mk("lnfactorial", v))
  }
  if (fn == "qlogis") {          # logit transform ln(p/(1-p))
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(.mk("logit", v))
  }

  # --- row-wise functions ---
  if (fn %in% c("pmax", "pmin")) {
    fn_m <- if (fn == "pmax") "rowmax" else "rowmin"
    clean <- args[!names(args) %in% "na.rm"]   # drop na.rm
    parts <- sapply(clean, translate_expr, df_name = df_name)
    if (!any(sapply(parts, is.null)))
      return(paste0(fn_m, "(", paste(unlist(parts), collapse = ", "), ")"))
  }
  if (fn %in% c("paste", "paste0")) {
    sep_node <- args[["sep"]]
    sep_str  <- if (fn == "paste0") ""
                else if (!is.null(sep_node) && is.character(sep_node)) sep_node
                else " "
    # translate positional (non-keyword) args only
    val_args <- args[!names(args) %in% c("sep", "collapse")]
    parts    <- sapply(val_args, translate_expr, df_name = df_name)
    if (!any(sapply(parts, is.null))) {
      if (nzchar(sep_str)) {
        sep_q    <- paste0("'", sep_str, "'")
        interl   <- unlist(lapply(seq_along(parts), function(i)
          if (i < length(parts)) c(parts[[i]], sep_q) else parts[[i]]))
        return(paste0("rowconcat(", paste(interl, collapse = ", "), ")"))
      }
      return(paste0("rowconcat(", paste(unlist(parts), collapse = ", "), ")"))
    }
  }

  # --- date construction / formatting ---
  if (fn %in% c("make_date", "lubridate::make_date", "ISOdate") && length(args) >= 3) {
    y <- translate_expr(args[[1]], df_name)
    m <- translate_expr(args[[2]], df_name)
    d <- translate_expr(args[[3]], df_name)
    if (!is.null(y) && !is.null(m) && !is.null(d)) return(.mk("date", y, m, d))
  }
  if (fn == "format" && length(args) >= 2) {
    fmt_node <- args[["format"]] %||% args[[2]]
    if (is.character(fmt_node) && fmt_node == "%Y-%m-%d") {
      v <- translate_expr(args[[1]], df_name)
      if (!is.null(v)) return(.mk("isoformatdate", v))
    }
  }
  if (fn %in% c("semester", "lubridate::semester")) {
    v <- translate_expr(args[[1]], df_name)
    if (!is.null(v)) return(.mk("halfyear", v))
  }

  # --- rowMeans / rowSums → rowmean / rowtotal ---
  if (fn %in% c("rowMeans", "rowSums")) {
    fn_m  <- if (fn == "rowMeans") "rowmean" else "rowtotal"
    inner <- args[[1]]
    parts <- NULL
    if (is.call(inner)) {
      ifn <- as.character(inner[[1]])
      if (ifn == "cbind") {
        tr <- sapply(as.list(inner)[-1], translate_expr, df_name = df_name)
        if (!any(sapply(tr, is.null))) parts <- unlist(tr)
      } else if (ifn == "[" && length(as.list(inner)) >= 3) {
        col_arg <- as.list(inner)[[3]]
        if (is.call(col_arg) && as.character(col_arg[[1]]) == "c") {
          cnames <- sapply(as.list(col_arg)[-1], function(a)
            if (is.character(a)) a else if (is.name(a)) as.character(a) else NULL)
          if (!any(sapply(cnames, is.null))) parts <- unlist(cnames)
        }
      }
    }
    if (!is.null(parts))
      return(paste0(fn_m, "(", paste(parts, collapse = ", "), ")"))
  }

  # --- dplyr::ntile → quantile ---
  if (fn %in% c("ntile", "dplyr::ntile") && length(args) >= 2) {
    x <- translate_expr(args[[1]], df_name)
    n <- translate_expr(args[[2]], df_name)
    if (!is.null(x) && !is.null(n)) return(.mk("quantile", x, n))
  }

  # --- microdata-native functions pass through ---
  if (fn %in% MICRODATA_FUNCS) {
    tr_args <- sapply(args, translate_expr, df_name = df_name)
    if (!any(sapply(tr_args, is.null)))
      return(paste0(fn, "(", paste(tr_args, collapse = ", "), ")"))
  }

  NULL  # untranslatable
}
