// GENERERT av tools/gen_jmv_specs.py — ikke rediger for hånd.
window.JMV_SPECS = {
 "descriptives": {
  "name": "descriptives",
  "ns": "jmv",
  "title": "Descriptives",
  "menuGroup": "Exploration",
  "menuSubgroup": "",
  "menuTitle": "Descriptives",
  "menuSubtitle": "",
  "options": [
   {
    "name": "vars",
    "type": "Variables",
    "title": "Variables",
    "default": null,
    "suggested": [],
    "permitted": [
     "numeric",
     "factor",
     "id"
    ]
   },
   {
    "name": "splitBy",
    "type": "Variables",
    "title": "Split by",
    "default": null,
    "suggested": [
     "nominal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "freq",
    "type": "Bool",
    "title": "Frequency tables",
    "default": false
   },
   {
    "name": "desc",
    "type": "List",
    "title": "Descriptives",
    "default": "columns",
    "choices": [
     {
      "value": "rows",
      "title": "Variables across rows"
     },
     {
      "value": "columns",
      "title": "Variables across columns"
     }
    ]
   },
   {
    "name": "hist",
    "type": "Bool",
    "title": "Histogram",
    "default": false
   },
   {
    "name": "dens",
    "type": "Bool",
    "title": "Density",
    "default": false
   },
   {
    "name": "bar",
    "type": "Bool",
    "title": "Bar plot",
    "default": false
   },
   {
    "name": "box",
    "type": "Bool",
    "title": "Box plot",
    "default": false
   },
   {
    "name": "violin",
    "type": "Bool",
    "title": "Violin",
    "default": false
   },
   {
    "name": "dot",
    "type": "Bool",
    "title": "Data",
    "default": false
   },
   {
    "name": "dotType",
    "type": "List",
    "title": "dotType",
    "default": "jitter",
    "choices": [
     {
      "value": "jitter",
      "title": "Jittered"
     },
     {
      "value": "stack",
      "title": "Stacked"
     }
    ]
   },
   {
    "name": "boxMean",
    "type": "Bool",
    "title": "Mean",
    "default": false
   },
   {
    "name": "boxLabelOutliers",
    "type": "Bool",
    "title": "Label outliers",
    "default": true
   },
   {
    "name": "qq",
    "type": "Bool",
    "title": "Q-Q plot",
    "default": false
   },
   {
    "name": "n",
    "type": "Bool",
    "title": "N",
    "default": true
   },
   {
    "name": "missing",
    "type": "Bool",
    "title": "Missing",
    "default": true
   },
   {
    "name": "mean",
    "type": "Bool",
    "title": "Mean",
    "default": true
   },
   {
    "name": "median",
    "type": "Bool",
    "title": "Median",
    "default": true
   },
   {
    "name": "mode",
    "type": "Bool",
    "title": "Mode",
    "default": false
   },
   {
    "name": "sum",
    "type": "Bool",
    "title": "Sum",
    "default": false
   },
   {
    "name": "sd",
    "type": "Bool",
    "title": "Standard deviation",
    "default": true
   },
   {
    "name": "variance",
    "type": "Bool",
    "title": "Variance",
    "default": false
   },
   {
    "name": "range",
    "type": "Bool",
    "title": "Range",
    "default": false
   },
   {
    "name": "min",
    "type": "Bool",
    "title": "Minimum",
    "default": true
   },
   {
    "name": "max",
    "type": "Bool",
    "title": "Maximum",
    "default": true
   },
   {
    "name": "se",
    "type": "Bool",
    "title": "Standard error",
    "default": false
   },
   {
    "name": "ci",
    "type": "Bool",
    "title": "Confidence Interval",
    "default": false
   },
   {
    "name": "ciWidth",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "iqr",
    "type": "Bool",
    "title": "IQR",
    "default": false
   },
   {
    "name": "skew",
    "type": "Bool",
    "title": "Skewness",
    "default": false
   },
   {
    "name": "kurt",
    "type": "Bool",
    "title": "Kurtosis",
    "default": false
   },
   {
    "name": "sw",
    "type": "Bool",
    "title": "Shapiro-Wilk",
    "default": false
   },
   {
    "name": "pcEqGr",
    "type": "Bool",
    "title": "Cut points for",
    "default": false
   },
   {
    "name": "pcNEqGr",
    "type": "Integer",
    "title": "Cut point values",
    "default": 4,
    "min": 2,
    "max": 10
   },
   {
    "name": "pc",
    "type": "Bool",
    "title": "Percentile",
    "default": false
   },
   {
    "name": "pcValues",
    "type": "String",
    "title": "Percentile values",
    "default": "25,50,75"
   },
   {
    "name": "extreme",
    "type": "Bool",
    "title": "Extreme values",
    "default": false
   },
   {
    "name": "extremeN",
    "type": "Integer",
    "title": "Number of extreme values",
    "default": 5,
    "min": 1,
    "max": 20
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "vars"
      },
      {
       "name": "splitBy"
      }
     ]
    },
    {
     "t": "grid",
     "cells": [
      {
       "col": 0,
       "row": 0,
       "children": [
        {
         "t": "combo",
         "name": "desc",
         "label": ""
        }
       ]
      },
      {
       "col": 1,
       "row": 0,
       "children": [
        {
         "t": "check",
         "name": "freq",
         "label": "Frequency tables"
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Statistics",
     "collapsed": true,
     "children": [
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Sample Size",
           "children": [
            {
             "t": "check",
             "name": "n"
            },
            {
             "t": "check",
             "name": "missing"
            }
           ]
          },
          {
           "t": "label",
           "label": "Percentile Values",
           "children": [
            {
             "t": "check",
             "name": "pcEqGr",
             "label": "Cut points for",
             "children": [
              {
               "t": "text",
               "name": "pcNEqGr",
               "label": "",
               "format": "number",
               "enable": "pcEqGr"
              }
             ]
            },
            {
             "t": "check",
             "name": "pc",
             "label": "Percentiles",
             "children": [
              {
               "t": "text",
               "name": "pcValues",
               "label": "",
               "format": "string",
               "enable": "pc"
              }
             ]
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Central Tendency",
           "children": [
            {
             "t": "check",
             "name": "mean"
            },
            {
             "t": "check",
             "name": "median"
            },
            {
             "t": "check",
             "name": "mode"
            },
            {
             "t": "check",
             "name": "sum"
            }
           ]
          }
         ]
        },
        {
         "col": 0,
         "row": 1,
         "children": [
          {
           "t": "label",
           "label": "Dispersion",
           "children": [
            {
             "t": "check",
             "name": "sd",
             "label": "Std. deviation"
            },
            {
             "t": "check",
             "name": "variance"
            },
            {
             "t": "check",
             "name": "range"
            },
            {
             "t": "check",
             "name": "min"
            },
            {
             "t": "check",
             "name": "max"
            },
            {
             "t": "check",
             "name": "iqr"
            }
           ]
          },
          {
           "t": "label",
           "label": "Mean Dispersion",
           "children": [
            {
             "t": "check",
             "name": "se",
             "label": "Std. error of Mean"
            },
            {
             "t": "check",
             "name": "ci",
             "label": "Confidence interval for Mean",
             "children": [
              {
               "t": "text",
               "name": "ciWidth",
               "label": "",
               "format": "number",
               "enable": "ci"
              }
             ]
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 1,
         "children": [
          {
           "t": "label",
           "label": "Distribution",
           "children": [
            {
             "t": "check",
             "name": "skew"
            },
            {
             "t": "check",
             "name": "kurt"
            }
           ]
          },
          {
           "t": "label",
           "label": "Normality",
           "children": [
            {
             "t": "check",
             "name": "sw"
            }
           ]
          },
          {
           "t": "label",
           "label": "Outliers",
           "children": [
            {
             "t": "check",
             "name": "extreme",
             "label": "Most extreme",
             "children": [
              {
               "t": "text",
               "name": "extremeN",
               "label": "",
               "format": "number",
               "enable": "extreme"
              }
             ]
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Plots",
     "collapsed": true,
     "children": [
      {
       "t": "label",
       "label": "Histograms",
       "children": [
        {
         "t": "check",
         "name": "hist"
        },
        {
         "t": "check",
         "name": "dens"
        }
       ]
      },
      {
       "t": "label",
       "label": "Q-Q Plots",
       "children": [
        {
         "t": "check",
         "name": "qq",
         "label": "Q-Q"
        }
       ]
      },
      {
       "t": "label",
       "label": "Box Plots",
       "children": [
        {
         "t": "check",
         "name": "box",
         "children": [
          {
           "t": "check",
           "name": "boxLabelOutliers",
           "enable": "box"
          }
         ]
        },
        {
         "t": "check",
         "name": "violin"
        },
        {
         "t": "check",
         "name": "dot",
         "children": [
          {
           "t": "combo",
           "name": "dotType",
           "label": "",
           "enable": "dot"
          }
         ]
        },
        {
         "t": "check",
         "name": "boxMean"
        }
       ]
      },
      {
       "t": "label",
       "label": "Bar Plots",
       "children": [
        {
         "t": "check",
         "name": "bar"
        }
       ]
      }
     ]
    }
   ]
  }
 },
 "ttestIS": {
  "name": "ttestIS",
  "ns": "jmv",
  "title": "Independent Samples T-Test",
  "menuGroup": "T-Tests",
  "menuSubgroup": "",
  "menuTitle": "Independent Samples T-Test",
  "menuSubtitle": "",
  "options": [
   {
    "name": "vars",
    "type": "Variables",
    "title": "Dependent Variables",
    "default": null,
    "suggested": [
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "group",
    "type": "Variable",
    "title": "Grouping Variable",
    "default": null,
    "suggested": [
     "nominal",
     "ordinal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "students",
    "type": "Bool",
    "title": "Student's",
    "default": true
   },
   {
    "name": "bf",
    "type": "Bool",
    "title": "Bayes factor",
    "default": false
   },
   {
    "name": "bfPrior",
    "type": "Number",
    "title": "Prior width",
    "default": 0.707,
    "min": 0.01,
    "max": 2
   },
   {
    "name": "welchs",
    "type": "Bool",
    "title": "Welch's",
    "default": false
   },
   {
    "name": "mann",
    "type": "Bool",
    "title": "Mann-Whitney U",
    "default": false
   },
   {
    "name": "hypothesis",
    "type": "List",
    "title": "Alternative hypothesis",
    "default": "different",
    "choices": [
     {
      "value": "different",
      "title": "Group 1 ≠ Group 2"
     },
     {
      "value": "oneGreater",
      "title": "Group 1 > Group 2"
     },
     {
      "value": "twoGreater",
      "title": "Group 1 < Group 2"
     }
    ]
   },
   {
    "name": "norm",
    "type": "Bool",
    "title": "Normality test",
    "default": false
   },
   {
    "name": "qq",
    "type": "Bool",
    "title": "Q-Q plot",
    "default": false
   },
   {
    "name": "eqv",
    "type": "Bool",
    "title": "Homogeneity test",
    "default": false
   },
   {
    "name": "meanDiff",
    "type": "Bool",
    "title": "Mean difference",
    "default": false
   },
   {
    "name": "ci",
    "type": "Bool",
    "title": "Confidence Interval",
    "default": false
   },
   {
    "name": "ciWidth",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "effectSize",
    "type": "Bool",
    "title": "Effect Size",
    "default": false
   },
   {
    "name": "ciES",
    "type": "Bool",
    "title": "Confidence Interval",
    "default": false
   },
   {
    "name": "ciWidthES",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "desc",
    "type": "Bool",
    "title": "Descriptives Table",
    "default": false
   },
   {
    "name": "plots",
    "type": "Bool",
    "title": "Descriptives Plots",
    "default": false
   },
   {
    "name": "miss",
    "type": "List",
    "title": "Missing values",
    "default": "perAnalysis",
    "choices": [
     {
      "value": "perAnalysis",
      "title": "perAnalysis"
     },
     {
      "value": "listwise",
      "title": "listwise"
     }
    ]
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "vars"
      },
      {
       "name": "group",
       "max": 1
      }
     ]
    },
    {
     "t": "grid",
     "cells": [
      {
       "col": 0,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Tests",
         "children": [
          {
           "t": "check",
           "name": "students",
           "children": [
            {
             "t": "check",
             "name": "bf",
             "label": "Bayes factor",
             "children": [
              {
               "t": "text",
               "name": "bfPrior",
               "label": "Prior",
               "format": "number",
               "enable": "bf"
              }
             ]
            }
           ]
          },
          {
           "t": "check",
           "name": "welchs"
          },
          {
           "t": "check",
           "name": "mann"
          }
         ]
        },
        {
         "t": "label",
         "label": "Hypothesis",
         "children": [
          {
           "t": "radio",
           "option": "hypothesis",
           "part": "different",
           "label": "Group 1 ≠ Group 2"
          },
          {
           "t": "radio",
           "option": "hypothesis",
           "part": "oneGreater",
           "label": "Group 1 > Group 2"
          },
          {
           "t": "radio",
           "option": "hypothesis",
           "part": "twoGreater",
           "label": "Group 1 < Group 2"
          }
         ]
        },
        {
         "t": "label",
         "label": "Missing values",
         "children": [
          {
           "t": "radio",
           "option": "miss",
           "part": "perAnalysis",
           "label": "Exclude cases analysis by analysis"
          },
          {
           "t": "radio",
           "option": "miss",
           "part": "listwise",
           "label": "Exclude cases listwise"
          }
         ]
        }
       ]
      },
      {
       "col": 1,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Additional Statistics",
         "children": [
          {
           "t": "check",
           "name": "meanDiff",
           "label": "Mean difference",
           "children": [
            {
             "t": "check",
             "name": "ci",
             "label": "Confidence interval",
             "children": [
              {
               "t": "text",
               "name": "ciWidth",
               "label": "",
               "format": "number"
              }
             ],
             "enable": "meanDiff"
            }
           ]
          },
          {
           "t": "check",
           "name": "effectSize",
           "label": "Effect size",
           "children": [
            {
             "t": "check",
             "name": "ciES",
             "label": "Confidence interval",
             "children": [
              {
               "t": "text",
               "name": "ciWidthES",
               "label": "",
               "format": "number"
              }
             ],
             "enable": "effectSize"
            }
           ]
          },
          {
           "t": "check",
           "name": "desc",
           "label": "Descriptives"
          },
          {
           "t": "check",
           "name": "plots",
           "label": "Descriptives plots"
          }
         ]
        },
        {
         "t": "label",
         "label": "Assumption Checks",
         "children": [
          {
           "t": "check",
           "name": "eqv"
          },
          {
           "t": "check",
           "name": "norm"
          },
          {
           "t": "check",
           "name": "qq"
          }
         ]
        }
       ]
      }
     ]
    }
   ]
  }
 },
 "ttestPS": {
  "name": "ttestPS",
  "ns": "jmv",
  "title": "Paired Samples T-Test",
  "menuGroup": "T-Tests",
  "menuSubgroup": "",
  "menuTitle": "Paired Samples T-Test",
  "menuSubtitle": "",
  "options": [
   {
    "name": "pairs",
    "type": "Pairs",
    "title": "Paired Variables",
    "default": null,
    "suggested": [
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "students",
    "type": "Bool",
    "title": "Student's test",
    "default": true
   },
   {
    "name": "bf",
    "type": "Bool",
    "title": "Bayes factor",
    "default": false
   },
   {
    "name": "bfPrior",
    "type": "Number",
    "title": "Prior width",
    "default": 0.707,
    "min": 0.5,
    "max": 2
   },
   {
    "name": "wilcoxon",
    "type": "Bool",
    "title": "Wilcoxon signed rank test",
    "default": false
   },
   {
    "name": "hypothesis",
    "type": "List",
    "title": "Alternative hypothesis",
    "default": "different",
    "choices": [
     {
      "value": "different",
      "title": "different"
     },
     {
      "value": "oneGreater",
      "title": "oneGreater"
     },
     {
      "value": "twoGreater",
      "title": "twoGreater"
     }
    ]
   },
   {
    "name": "norm",
    "type": "Bool",
    "title": "Normality test",
    "default": false
   },
   {
    "name": "qq",
    "type": "Bool",
    "title": "Q-Q Plot",
    "default": false
   },
   {
    "name": "meanDiff",
    "type": "Bool",
    "title": "Mean difference",
    "default": false
   },
   {
    "name": "ci",
    "type": "Bool",
    "title": "Confidence Interval",
    "default": false
   },
   {
    "name": "ciWidth",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "effectSize",
    "type": "Bool",
    "title": "Effect Size",
    "default": false
   },
   {
    "name": "ciES",
    "type": "Bool",
    "title": "Confidence Interval",
    "default": false
   },
   {
    "name": "ciWidthES",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "desc",
    "type": "Bool",
    "title": "Descriptives Table",
    "default": false
   },
   {
    "name": "plots",
    "type": "Bool",
    "title": "Descriptives Plots",
    "default": false
   },
   {
    "name": "miss",
    "type": "List",
    "title": "Missing values",
    "default": "perAnalysis",
    "choices": [
     {
      "value": "perAnalysis",
      "title": "perAnalysis"
     },
     {
      "value": "listwise",
      "title": "listwise"
     }
    ]
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "pairs"
      }
     ]
    },
    {
     "t": "grid",
     "cells": [
      {
       "col": 0,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Tests",
         "children": [
          {
           "t": "check",
           "name": "students",
           "label": "Student's",
           "children": [
            {
             "t": "check",
             "name": "bf",
             "label": "Bayes factor",
             "children": [
              {
               "t": "text",
               "name": "bfPrior",
               "label": "Prior",
               "format": "number",
               "enable": "bf"
              }
             ]
            }
           ]
          },
          {
           "t": "check",
           "name": "wilcoxon",
           "label": "Wilcoxon rank"
          }
         ]
        },
        {
         "t": "label",
         "label": "Hypothesis",
         "children": [
          {
           "t": "radio",
           "option": "hypothesis",
           "part": "different",
           "label": "Measure 1 ≠ Measure 2"
          },
          {
           "t": "radio",
           "option": "hypothesis",
           "part": "oneGreater",
           "label": "Measure 1 > Measure 2"
          },
          {
           "t": "radio",
           "option": "hypothesis",
           "part": "twoGreater",
           "label": "Measure 1 < Measure 2"
          }
         ]
        },
        {
         "t": "label",
         "label": "Missing values",
         "children": [
          {
           "t": "radio",
           "option": "miss",
           "part": "perAnalysis",
           "label": "Exclude cases analysis by analysis"
          },
          {
           "t": "radio",
           "option": "miss",
           "part": "listwise",
           "label": "Exclude cases listwise"
          }
         ]
        }
       ]
      },
      {
       "col": 1,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Additional Statistics",
         "children": [
          {
           "t": "check",
           "name": "meanDiff",
           "label": "Mean difference",
           "children": [
            {
             "t": "check",
             "name": "ci",
             "label": "Confidence interval",
             "children": [
              {
               "t": "text",
               "name": "ciWidth",
               "label": "",
               "format": "number"
              }
             ],
             "enable": "meanDiff"
            }
           ]
          },
          {
           "t": "check",
           "name": "effectSize",
           "label": "Effect size",
           "children": [
            {
             "t": "check",
             "name": "ciES",
             "label": "Confidence interval",
             "children": [
              {
               "t": "text",
               "name": "ciWidthES",
               "label": "",
               "format": "number"
              }
             ],
             "enable": "effectSize"
            }
           ]
          },
          {
           "t": "check",
           "name": "desc",
           "label": "Descriptives"
          },
          {
           "t": "check",
           "name": "plots",
           "label": "Descriptives plots"
          }
         ]
        },
        {
         "t": "label",
         "label": "Assumption Checks",
         "children": [
          {
           "t": "check",
           "name": "norm"
          },
          {
           "t": "check",
           "name": "qq"
          }
         ]
        }
       ]
      }
     ]
    }
   ]
  }
 },
 "ttestOneS": {
  "name": "ttestOneS",
  "ns": "jmv",
  "title": "One Sample T-Test",
  "menuGroup": "T-Tests",
  "menuSubgroup": "",
  "menuTitle": "One Sample T-Test",
  "menuSubtitle": "",
  "options": [
   {
    "name": "vars",
    "type": "Variables",
    "title": "Dependent Variables",
    "default": null,
    "suggested": [
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "students",
    "type": "Bool",
    "title": "Student's test",
    "default": true
   },
   {
    "name": "bf",
    "type": "Bool",
    "title": "Bayes factor",
    "default": false
   },
   {
    "name": "bfPrior",
    "type": "Number",
    "title": "Prior width",
    "default": 0.707,
    "min": 0.5,
    "max": 2
   },
   {
    "name": "wilcoxon",
    "type": "Bool",
    "title": "Wilcoxon signed rank test",
    "default": false
   },
   {
    "name": "testValue",
    "type": "Number",
    "title": "Test Value",
    "default": 0
   },
   {
    "name": "hypothesis",
    "type": "List",
    "title": "Alternative hypothesis",
    "default": "dt",
    "choices": [
     {
      "value": "dt",
      "title": "dt"
     },
     {
      "value": "gt",
      "title": "gt"
     },
     {
      "value": "lt",
      "title": "lt"
     }
    ]
   },
   {
    "name": "norm",
    "type": "Bool",
    "title": "Normality test",
    "default": false
   },
   {
    "name": "qq",
    "type": "Bool",
    "title": "Q-Q Plot",
    "default": false
   },
   {
    "name": "meanDiff",
    "type": "Bool",
    "title": "Mean difference",
    "default": false
   },
   {
    "name": "ci",
    "type": "Bool",
    "title": "Confidence Interval",
    "default": false
   },
   {
    "name": "ciWidth",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "effectSize",
    "type": "Bool",
    "title": "Effect size",
    "default": false
   },
   {
    "name": "ciES",
    "type": "Bool",
    "title": "Confidence Interval",
    "default": false
   },
   {
    "name": "ciWidthES",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "desc",
    "type": "Bool",
    "title": "Descriptives Table",
    "default": false
   },
   {
    "name": "plots",
    "type": "Bool",
    "title": "Descriptives Plots",
    "default": false
   },
   {
    "name": "miss",
    "type": "List",
    "title": "Missing values",
    "default": "perAnalysis",
    "choices": [
     {
      "value": "perAnalysis",
      "title": "perAnalysis"
     },
     {
      "value": "listwise",
      "title": "listwise"
     }
    ]
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "vars"
      }
     ]
    },
    {
     "t": "grid",
     "cells": [
      {
       "col": 0,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Tests",
         "children": [
          {
           "t": "check",
           "name": "students",
           "label": "Student's",
           "children": [
            {
             "t": "check",
             "name": "bf",
             "label": "Bayes factor",
             "children": [
              {
               "t": "text",
               "name": "bfPrior",
               "label": "Prior",
               "format": "number",
               "enable": "bf"
              }
             ]
            }
           ]
          },
          {
           "t": "check",
           "name": "wilcoxon",
           "label": "Wilcoxon rank"
          }
         ]
        },
        {
         "t": "label",
         "label": "Hypothesis",
         "children": [
          {
           "t": "text",
           "name": "testValue",
           "label": "Test value",
           "format": "number"
          },
          {
           "t": "radio",
           "option": "hypothesis",
           "part": "dt",
           "label": "≠ Test value"
          },
          {
           "t": "radio",
           "option": "hypothesis",
           "part": "gt",
           "label": "> Test value"
          },
          {
           "t": "radio",
           "option": "hypothesis",
           "part": "lt",
           "label": "< Test value"
          }
         ]
        },
        {
         "t": "label",
         "label": "Missing values",
         "children": [
          {
           "t": "radio",
           "option": "miss",
           "part": "perAnalysis",
           "label": "Exclude cases analysis by analysis"
          },
          {
           "t": "radio",
           "option": "miss",
           "part": "listwise",
           "label": "Exclude cases listwise"
          }
         ]
        }
       ]
      },
      {
       "col": 1,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Additional Statistics",
         "children": [
          {
           "t": "check",
           "name": "meanDiff",
           "label": "Mean difference",
           "children": [
            {
             "t": "check",
             "name": "ci",
             "label": "Confidence interval",
             "children": [
              {
               "t": "text",
               "name": "ciWidth",
               "label": "",
               "format": "number"
              }
             ],
             "enable": "meanDiff"
            }
           ]
          },
          {
           "t": "check",
           "name": "effectSize",
           "label": "Effect size",
           "children": [
            {
             "t": "check",
             "name": "ciES",
             "label": "Confidence interval",
             "children": [
              {
               "t": "text",
               "name": "ciWidthES",
               "label": "",
               "format": "number"
              }
             ],
             "enable": "effectSize"
            }
           ]
          },
          {
           "t": "check",
           "name": "desc",
           "label": "Descriptives"
          },
          {
           "t": "check",
           "name": "plots",
           "label": "Descriptives plots"
          }
         ]
        },
        {
         "t": "label",
         "label": "Assumption Checks",
         "children": [
          {
           "t": "check",
           "name": "norm"
          },
          {
           "t": "check",
           "name": "qq"
          }
         ]
        }
       ]
      }
     ]
    }
   ]
  }
 },
 "anovaOneW": {
  "name": "anovaOneW",
  "ns": "jmv",
  "title": "One-Way ANOVA",
  "menuGroup": "ANOVA",
  "menuSubgroup": "",
  "menuTitle": "One-Way ANOVA",
  "menuSubtitle": "",
  "options": [
   {
    "name": "deps",
    "type": "Variables",
    "title": "Dependent Variables",
    "default": null,
    "suggested": [
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "group",
    "type": "Variable",
    "title": "Grouping Variable",
    "default": null,
    "suggested": [
     "nominal",
     "ordinal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "welchs",
    "type": "Bool",
    "title": "Don't assume equal (Welch's)",
    "default": true
   },
   {
    "name": "fishers",
    "type": "Bool",
    "title": "Assume equal (Fisher's)",
    "default": false
   },
   {
    "name": "miss",
    "type": "List",
    "title": "Missing values exclusion method",
    "default": "perAnalysis",
    "choices": [
     {
      "value": "perAnalysis",
      "title": "perAnalysis"
     },
     {
      "value": "listwise",
      "title": "listwise"
     }
    ]
   },
   {
    "name": "desc",
    "type": "Bool",
    "title": "Descriptives table",
    "default": false
   },
   {
    "name": "descPlot",
    "type": "Bool",
    "title": "Descriptives plots",
    "default": false
   },
   {
    "name": "norm",
    "type": "Bool",
    "title": "Normality test",
    "default": false
   },
   {
    "name": "qq",
    "type": "Bool",
    "title": "Q-Q Plot",
    "default": false
   },
   {
    "name": "eqv",
    "type": "Bool",
    "title": "Homogeneity test",
    "default": false
   },
   {
    "name": "phMethod",
    "type": "List",
    "title": "Post-Hoc Tests",
    "default": "none",
    "choices": [
     {
      "value": "none",
      "title": "none"
     },
     {
      "value": "gamesHowell",
      "title": "gamesHowell"
     },
     {
      "value": "tukey",
      "title": "tukey"
     }
    ]
   },
   {
    "name": "phMeanDif",
    "type": "Bool",
    "title": "Mean difference",
    "default": true
   },
   {
    "name": "phSig",
    "type": "Bool",
    "title": "Report significance",
    "default": true
   },
   {
    "name": "phTest",
    "type": "Bool",
    "title": "Test results (t and df)",
    "default": false
   },
   {
    "name": "phFlag",
    "type": "Bool",
    "title": "Flag significant comparisons",
    "default": false
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "deps"
      },
      {
       "name": "group",
       "max": 1
      }
     ]
    },
    {
     "t": "grid",
     "cells": [
      {
       "col": 0,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Variances",
         "children": [
          {
           "t": "check",
           "name": "welchs"
          },
          {
           "t": "check",
           "name": "fishers"
          }
         ]
        },
        {
         "t": "label",
         "label": "Missing Values",
         "children": [
          {
           "t": "radio",
           "option": "miss",
           "part": "perAnalysis",
           "label": "Exclude cases analysis by analysis"
          },
          {
           "t": "radio",
           "option": "miss",
           "part": "listwise",
           "label": "Exclude cases listwise"
          }
         ]
        }
       ]
      },
      {
       "col": 1,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Additional Statistics",
         "children": [
          {
           "t": "check",
           "name": "desc"
          },
          {
           "t": "check",
           "name": "descPlot"
          }
         ]
        },
        {
         "t": "label",
         "label": "Assumption Checks",
         "children": [
          {
           "t": "check",
           "name": "eqv"
          },
          {
           "t": "check",
           "name": "norm"
          },
          {
           "t": "check",
           "name": "qq"
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Post-Hoc Tests",
     "collapsed": true,
     "children": [
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Post-Hoc Test",
           "children": [
            {
             "t": "radio",
             "option": "phMethod",
             "part": "none",
             "label": "None"
            },
            {
             "t": "radio",
             "option": "phMethod",
             "part": "gamesHowell",
             "label": "Games-Howell (unequal variances)"
            },
            {
             "t": "radio",
             "option": "phMethod",
             "part": "tukey",
             "label": "Tukey (equal variances)"
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Statistics",
           "children": [
            {
             "t": "check",
             "name": "phMeanDif"
            },
            {
             "t": "check",
             "name": "phSig"
            },
            {
             "t": "check",
             "name": "phTest"
            },
            {
             "t": "check",
             "name": "phFlag"
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    }
   ]
  }
 },
 "anova": {
  "name": "anova",
  "ns": "jmv",
  "title": "ANOVA",
  "menuGroup": "ANOVA",
  "menuSubgroup": "",
  "menuTitle": "ANOVA",
  "menuSubtitle": "",
  "options": [
   {
    "name": "dep",
    "type": "Variable",
    "title": "Dependent Variable",
    "default": null,
    "suggested": [
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "factors",
    "type": "Variables",
    "title": "Fixed Factors",
    "default": null,
    "suggested": [
     "nominal",
     "ordinal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "effectSize",
    "type": "NMXList",
    "title": "Effect Size",
    "default": null,
    "choices": [
     {
      "value": "eta",
      "title": "η²"
     },
     {
      "value": "partEta",
      "title": "partial η²"
     },
     {
      "value": "omega",
      "title": "ω²"
     }
    ]
   },
   {
    "name": "modelTest",
    "type": "Bool",
    "title": "Overall model test",
    "default": false
   },
   {
    "name": "modelTerms",
    "type": "Terms",
    "title": "Model Terms",
    "default": null
   },
   {
    "name": "ss",
    "type": "List",
    "title": "Sum of squares",
    "default": "3",
    "choices": [
     {
      "value": "1",
      "title": "Type 1"
     },
     {
      "value": "2",
      "title": "Type 2"
     },
     {
      "value": "3",
      "title": "Type 3"
     }
    ]
   },
   {
    "name": "homo",
    "type": "Bool",
    "title": "Homogeneity test",
    "default": false
   },
   {
    "name": "norm",
    "type": "Bool",
    "title": "Normality test",
    "default": false
   },
   {
    "name": "qq",
    "type": "Bool",
    "title": "Q-Q Plot",
    "default": false
   },
   {
    "name": "contrasts",
    "type": "Array",
    "title": "Contrasts",
    "default": null
   },
   {
    "name": "postHoc",
    "type": "Terms",
    "title": "Post Hoc Tests",
    "default": null
   },
   {
    "name": "postHocCorr",
    "type": "NMXList",
    "title": "Correction",
    "default": [
     "tukey"
    ],
    "choices": [
     {
      "value": "none",
      "title": "No correction"
     },
     {
      "value": "tukey",
      "title": "Tukey"
     },
     {
      "value": "scheffe",
      "title": "Scheffe"
     },
     {
      "value": "bonf",
      "title": "Bonferroni"
     },
     {
      "value": "holm",
      "title": "Holm"
     }
    ]
   },
   {
    "name": "postHocES",
    "type": "NMXList",
    "title": "Effect size",
    "default": [],
    "choices": [
     {
      "value": "d",
      "title": "Cohen's d"
     }
    ]
   },
   {
    "name": "postHocEsCi",
    "type": "Bool",
    "title": "Confidence Interval",
    "default": false
   },
   {
    "name": "postHocEsCiWidth",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "emMeans",
    "type": "Array",
    "title": "Marginal Means",
    "default": [
     []
    ]
   },
   {
    "name": "emmPlots",
    "type": "Bool",
    "title": "Marginal means plots",
    "default": true
   },
   {
    "name": "emmPlotData",
    "type": "Bool",
    "title": "Observed scores",
    "default": false
   },
   {
    "name": "emmPlotError",
    "type": "List",
    "title": "Error bars",
    "default": "ci",
    "choices": [
     {
      "value": "none",
      "title": "None"
     },
     {
      "value": "ci",
      "title": "Confidence interval"
     },
     {
      "value": "se",
      "title": "Standard Error"
     }
    ]
   },
   {
    "name": "emmTables",
    "type": "Bool",
    "title": "Marginal means tables",
    "default": false
   },
   {
    "name": "emmWeights",
    "type": "Bool",
    "title": "Equal cell weights",
    "default": true
   },
   {
    "name": "ciWidthEmm",
    "type": "Number",
    "title": "Confidence interval width",
    "default": 95,
    "min": 50,
    "max": 99.9
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "dep",
       "max": 1
      },
      {
       "name": "factors"
      }
     ]
    },
    {
     "t": "grid",
     "cells": [
      {
       "col": 0,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Model Fit",
         "children": [
          {
           "t": "check",
           "name": "modelTest"
          }
         ]
        }
       ]
      },
      {
       "col": 1,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Effect Size",
         "children": [
          {
           "t": "checkpart",
           "option": "effectSize",
           "part": "eta",
           "label": "eta"
          },
          {
           "t": "checkpart",
           "option": "effectSize",
           "part": "partEta",
           "label": "partEta"
          },
          {
           "t": "checkpart",
           "option": "effectSize",
           "part": "omega",
           "label": "omega"
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Model",
     "collapsed": true,
     "children": [
      {
       "t": "combo",
       "name": "ss",
       "label": ""
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Assumption Checks",
     "collapsed": true,
     "children": [
      {
       "t": "check",
       "name": "homo"
      },
      {
       "t": "check",
       "name": "norm"
      },
      {
       "t": "check",
       "name": "qq"
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Post Hoc Tests",
     "collapsed": true,
     "children": [
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Correction",
           "children": [
            {
             "t": "checkpart",
             "option": "postHocCorr",
             "part": "none",
             "label": "none"
            },
            {
             "t": "checkpart",
             "option": "postHocCorr",
             "part": "tukey",
             "label": "tukey"
            },
            {
             "t": "checkpart",
             "option": "postHocCorr",
             "part": "scheffe",
             "label": "scheffe"
            },
            {
             "t": "checkpart",
             "option": "postHocCorr",
             "part": "bonf",
             "label": "bonf"
            },
            {
             "t": "checkpart",
             "option": "postHocCorr",
             "part": "holm",
             "label": "holm"
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Effect Size",
           "children": [
            {
             "t": "checkpart",
             "option": "postHocES",
             "part": "d",
             "label": "d",
             "children": [
              {
               "t": "check",
               "name": "postHocEsCi",
               "label": "Confidence interval",
               "children": [
                {
                 "t": "text",
                 "name": "postHocEsCiWidth",
                 "label": "",
                 "format": "number"
                }
               ]
              }
             ]
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Estimated Marginal Means",
     "collapsed": true,
     "children": [
      {
       "t": "supplier",
       "targets": []
      },
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Output",
           "children": [
            {
             "t": "check",
             "name": "emmPlots"
            },
            {
             "t": "check",
             "name": "emmTables"
            }
           ]
          },
          {
           "t": "label",
           "label": "General Options",
           "children": [
            {
             "t": "check",
             "name": "emmWeights"
            },
            {
             "t": "text",
             "name": "ciWidthEmm",
             "label": "Confidence interval",
             "format": "number"
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Plot",
           "children": [
            {
             "t": "combo",
             "name": "emmPlotError",
             "label": ""
            },
            {
             "t": "check",
             "name": "emmPlotData"
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    }
   ]
  }
 },
 "ancova": {
  "name": "ancova",
  "ns": "jmv",
  "title": "ANCOVA",
  "menuGroup": "ANOVA",
  "menuSubgroup": "",
  "menuTitle": "ANCOVA",
  "menuSubtitle": "",
  "options": [
   {
    "name": "dep",
    "type": "Variable",
    "title": "Dependent Variable",
    "default": null,
    "suggested": [
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "factors",
    "type": "Variables",
    "title": "Fixed Factors",
    "default": null,
    "suggested": [
     "nominal",
     "ordinal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "covs",
    "type": "Variables",
    "title": "Covariates",
    "default": null,
    "suggested": [
     "continuous",
     "ordinal"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "effectSize",
    "type": "NMXList",
    "title": "Effect Size",
    "default": null,
    "choices": [
     {
      "value": "eta",
      "title": "η²"
     },
     {
      "value": "partEta",
      "title": "partial η²"
     },
     {
      "value": "omega",
      "title": "ω²"
     }
    ]
   },
   {
    "name": "modelTest",
    "type": "Bool",
    "title": "Overall model test",
    "default": false
   },
   {
    "name": "modelTerms",
    "type": "Terms",
    "title": "Model Terms",
    "default": null
   },
   {
    "name": "ss",
    "type": "List",
    "title": "Sum of squares",
    "default": "3",
    "choices": [
     {
      "value": "1",
      "title": "Type 1"
     },
     {
      "value": "2",
      "title": "Type 2"
     },
     {
      "value": "3",
      "title": "Type 3"
     }
    ]
   },
   {
    "name": "homo",
    "type": "Bool",
    "title": "Homogeneity test",
    "default": false
   },
   {
    "name": "norm",
    "type": "Bool",
    "title": "Normality test",
    "default": false
   },
   {
    "name": "qq",
    "type": "Bool",
    "title": "Q-Q Plot",
    "default": false
   },
   {
    "name": "contrasts",
    "type": "Array",
    "title": "Contrasts",
    "default": null
   },
   {
    "name": "postHoc",
    "type": "Terms",
    "title": "Post Hoc Tests",
    "default": null
   },
   {
    "name": "postHocCorr",
    "type": "NMXList",
    "title": "Correction",
    "default": [
     "tukey"
    ],
    "choices": [
     {
      "value": "none",
      "title": "No correction"
     },
     {
      "value": "tukey",
      "title": "Tukey"
     },
     {
      "value": "scheffe",
      "title": "Scheffe"
     },
     {
      "value": "bonf",
      "title": "Bonferroni"
     },
     {
      "value": "holm",
      "title": "Holm"
     }
    ]
   },
   {
    "name": "postHocES",
    "type": "NMXList",
    "title": "Effect size",
    "default": [],
    "choices": [
     {
      "value": "d",
      "title": "Cohen's d"
     }
    ]
   },
   {
    "name": "postHocEsCi",
    "type": "Bool",
    "title": "Confidence Interval",
    "default": false
   },
   {
    "name": "postHocEsCiWidth",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "emMeans",
    "type": "Array",
    "title": "Marginal Means",
    "default": [
     []
    ]
   },
   {
    "name": "emmPlots",
    "type": "Bool",
    "title": "Marginal means plots",
    "default": true
   },
   {
    "name": "emmPlotData",
    "type": "Bool",
    "title": "Observed scores",
    "default": false
   },
   {
    "name": "emmPlotError",
    "type": "List",
    "title": "Error bars",
    "default": "ci",
    "choices": [
     {
      "value": "none",
      "title": "None"
     },
     {
      "value": "ci",
      "title": "Confidence interval"
     },
     {
      "value": "se",
      "title": "Standard error"
     }
    ]
   },
   {
    "name": "emmTables",
    "type": "Bool",
    "title": "Marginal means tables",
    "default": false
   },
   {
    "name": "emmWeights",
    "type": "Bool",
    "title": "Equal cell weights",
    "default": true
   },
   {
    "name": "ciWidthEmm",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "dep",
       "max": 1
      },
      {
       "name": "factors"
      },
      {
       "name": "covs"
      }
     ]
    },
    {
     "t": "grid",
     "cells": [
      {
       "col": 0,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Model Fit",
         "children": [
          {
           "t": "check",
           "name": "modelTest"
          }
         ]
        }
       ]
      },
      {
       "col": 1,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Effect Size",
         "children": [
          {
           "t": "checkpart",
           "option": "effectSize",
           "part": "eta",
           "label": "eta"
          },
          {
           "t": "checkpart",
           "option": "effectSize",
           "part": "partEta",
           "label": "partEta"
          },
          {
           "t": "checkpart",
           "option": "effectSize",
           "part": "omega",
           "label": "omega"
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Model",
     "collapsed": true,
     "children": [
      {
       "t": "combo",
       "name": "ss",
       "label": ""
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Assumption Checks",
     "collapsed": true,
     "children": [
      {
       "t": "check",
       "name": "homo"
      },
      {
       "t": "check",
       "name": "norm"
      },
      {
       "t": "check",
       "name": "qq"
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Post Hoc Tests",
     "collapsed": true,
     "children": [
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Correction",
           "children": [
            {
             "t": "checkpart",
             "option": "postHocCorr",
             "part": "none",
             "label": "none"
            },
            {
             "t": "checkpart",
             "option": "postHocCorr",
             "part": "tukey",
             "label": "tukey"
            },
            {
             "t": "checkpart",
             "option": "postHocCorr",
             "part": "scheffe",
             "label": "scheffe"
            },
            {
             "t": "checkpart",
             "option": "postHocCorr",
             "part": "bonf",
             "label": "bonf"
            },
            {
             "t": "checkpart",
             "option": "postHocCorr",
             "part": "holm",
             "label": "holm"
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Effect Size",
           "children": [
            {
             "t": "checkpart",
             "option": "postHocES",
             "part": "d",
             "label": "d",
             "children": [
              {
               "t": "check",
               "name": "postHocEsCi",
               "label": "Confidence interval",
               "children": [
                {
                 "t": "text",
                 "name": "postHocEsCiWidth",
                 "label": "",
                 "format": "number"
                }
               ]
              }
             ]
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Estimated Marginal Means",
     "collapsed": true,
     "children": [
      {
       "t": "supplier",
       "targets": []
      },
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Output",
           "children": [
            {
             "t": "check",
             "name": "emmPlots"
            },
            {
             "t": "check",
             "name": "emmTables"
            }
           ]
          },
          {
           "t": "label",
           "label": "General Options",
           "children": [
            {
             "t": "check",
             "name": "emmWeights"
            },
            {
             "t": "text",
             "name": "ciWidthEmm",
             "label": "Confidence interval",
             "format": "number"
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Plot",
           "children": [
            {
             "t": "combo",
             "name": "emmPlotError",
             "label": ""
            },
            {
             "t": "check",
             "name": "emmPlotData"
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    }
   ]
  }
 },
 "mancova": {
  "name": "mancova",
  "ns": "jmv",
  "title": "MANCOVA",
  "menuGroup": "ANOVA",
  "menuSubgroup": "",
  "menuTitle": "MANCOVA",
  "menuSubtitle": "",
  "options": [
   {
    "name": "deps",
    "type": "Variables",
    "title": "Dependent Variables",
    "default": null,
    "suggested": [
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "factors",
    "type": "Variables",
    "title": "Factors",
    "default": null,
    "suggested": [
     "nominal",
     "ordinal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "covs",
    "type": "Variables",
    "title": "Covariates",
    "default": null,
    "suggested": [
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "multivar",
    "type": "NMXList",
    "title": "Multivariate Statistics",
    "default": [
     "pillai",
     "wilks",
     "hotel",
     "roy"
    ],
    "choices": [
     {
      "value": "pillai",
      "title": "Pillai's Trace"
     },
     {
      "value": "wilks",
      "title": "Wilks' Lambda"
     },
     {
      "value": "hotel",
      "title": "Hotelling's Trace"
     },
     {
      "value": "roy",
      "title": "Roy's Largest Root"
     }
    ]
   },
   {
    "name": "boxM",
    "type": "Bool",
    "title": "Box's M test for homogeneity of covariance matrices",
    "default": false
   },
   {
    "name": "shapiro",
    "type": "Bool",
    "title": "Shapiro-Wilk test for multivariate normality",
    "default": false
   },
   {
    "name": "qqPlot",
    "type": "Bool",
    "title": "Q-Q plot of multivariate normality",
    "default": false
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "deps"
      },
      {
       "name": "factors"
      },
      {
       "name": "covs"
      }
     ]
    },
    {
     "t": "grid",
     "cells": [
      {
       "col": 0,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Multivariate Statistics",
         "children": [
          {
           "t": "checkpart",
           "option": "multivar",
           "part": "pillai",
           "label": "pillai"
          },
          {
           "t": "checkpart",
           "option": "multivar",
           "part": "wilks",
           "label": "wilks"
          },
          {
           "t": "checkpart",
           "option": "multivar",
           "part": "hotel",
           "label": "hotel"
          },
          {
           "t": "checkpart",
           "option": "multivar",
           "part": "roy",
           "label": "roy"
          }
         ]
        }
       ]
      },
      {
       "col": 1,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Assumption Checks",
         "children": [
          {
           "t": "check",
           "name": "boxM",
           "label": "Box's M test"
          },
          {
           "t": "check",
           "name": "shapiro",
           "label": "Shapiro-Wilk test"
          },
          {
           "t": "check",
           "name": "qqPlot"
          }
         ]
        }
       ]
      }
     ]
    }
   ]
  }
 },
 "anovaNP": {
  "name": "anovaNP",
  "ns": "jmv",
  "title": "One-Way ANOVA (Non-parametric)",
  "menuGroup": "ANOVA",
  "menuSubgroup": "Non-Parametric",
  "menuTitle": "One-Way ANOVA",
  "menuSubtitle": "Kruskal-Wallis",
  "options": [
   {
    "name": "deps",
    "type": "Variables",
    "title": "Dependent Variables",
    "default": null,
    "suggested": [
     "continuous",
     "ordinal"
    ],
    "permitted": []
   },
   {
    "name": "group",
    "type": "Variable",
    "title": "Grouping Variable",
    "default": null,
    "suggested": [
     "nominal",
     "ordinal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "es",
    "type": "Bool",
    "title": "ε²",
    "default": false
   },
   {
    "name": "pairs",
    "type": "Bool",
    "title": "DSCF pairwise comparisons",
    "default": false
   },
   {
    "name": "pairsDunn",
    "type": "Bool",
    "title": "Dunn's pairwise comparisons",
    "default": false
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "deps"
      },
      {
       "name": "group",
       "max": 1
      }
     ]
    },
    {
     "t": "grid",
     "cells": [
      {
       "col": 0,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Effect Size",
         "children": [
          {
           "t": "check",
           "name": "es"
          }
         ]
        }
       ]
      },
      {
       "col": 1,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Post Hoc Tests",
         "children": [
          {
           "t": "check",
           "name": "pairs"
          },
          {
           "t": "check",
           "name": "pairsDunn"
          }
         ]
        }
       ]
      }
     ]
    }
   ]
  }
 },
 "anovaRMNP": {
  "name": "anovaRMNP",
  "ns": "jmv",
  "title": "Repeated Measures ANOVA (Non-parametric)",
  "menuGroup": "ANOVA",
  "menuSubgroup": "Non-Parametric",
  "menuTitle": "Repeated Measures ANOVA",
  "menuSubtitle": "Friedman",
  "options": [
   {
    "name": "measures",
    "type": "Variables",
    "title": "Measures",
    "default": null,
    "suggested": [
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "pairs",
    "type": "Bool",
    "title": "Pairwise comparisons (Durbin-Conover)",
    "default": false
   },
   {
    "name": "desc",
    "type": "Bool",
    "title": "Descriptives",
    "default": false
   },
   {
    "name": "plots",
    "type": "Bool",
    "title": "Descriptive plot",
    "default": false
   },
   {
    "name": "plotType",
    "type": "List",
    "title": "Plot Type",
    "default": "means",
    "choices": [
     {
      "value": "means",
      "title": "Means"
     },
     {
      "value": "medians",
      "title": "Medians"
     }
    ]
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "measures"
      }
     ]
    },
    {
     "t": "check",
     "name": "pairs"
    },
    {
     "t": "check",
     "name": "desc"
    },
    {
     "t": "check",
     "name": "plots",
     "children": [
      {
       "t": "radio",
       "option": "plotType",
       "part": "means",
       "label": "means",
       "enable": "plots"
      },
      {
       "t": "radio",
       "option": "plotType",
       "part": "medians",
       "label": "medians",
       "enable": "plots"
      }
     ]
    }
   ]
  }
 },
 "corrMatrix": {
  "name": "corrMatrix",
  "ns": "jmv",
  "title": "Correlation Matrix",
  "menuGroup": "Regression",
  "menuSubgroup": "",
  "menuTitle": "Correlation Matrix",
  "menuSubtitle": "",
  "options": [
   {
    "name": "vars",
    "type": "Variables",
    "title": "Variables",
    "default": null,
    "suggested": [
     "continuous",
     "ordinal"
    ],
    "permitted": [
     "numeric",
     "factor"
    ]
   },
   {
    "name": "pearson",
    "type": "Bool",
    "title": "Pearson",
    "default": true
   },
   {
    "name": "spearman",
    "type": "Bool",
    "title": "Spearman",
    "default": false
   },
   {
    "name": "kendall",
    "type": "Bool",
    "title": "Kendall's tau-b",
    "default": false
   },
   {
    "name": "sig",
    "type": "Bool",
    "title": "Report significance",
    "default": true
   },
   {
    "name": "flag",
    "type": "Bool",
    "title": "Flag significant correlations",
    "default": false
   },
   {
    "name": "n",
    "type": "Bool",
    "title": "N",
    "default": false
   },
   {
    "name": "ci",
    "type": "Bool",
    "title": "Confidence intervals",
    "default": false
   },
   {
    "name": "ciWidth",
    "type": "Number",
    "title": "Confidence interval width",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "plots",
    "type": "Bool",
    "title": "Correlation matrix",
    "default": false
   },
   {
    "name": "plotDens",
    "type": "Bool",
    "title": "Densities for variables",
    "default": false
   },
   {
    "name": "plotStats",
    "type": "Bool",
    "title": "Statistics",
    "default": false
   },
   {
    "name": "hypothesis",
    "type": "List",
    "title": "Hypothesis",
    "default": "corr",
    "choices": [
     {
      "value": "corr",
      "title": "Correlated"
     },
     {
      "value": "pos",
      "title": "Correlated positively"
     },
     {
      "value": "neg",
      "title": "Correlated negatively"
     }
    ]
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "vars"
      }
     ]
    },
    {
     "t": "grid",
     "cells": [
      {
       "col": 0,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Correlation Coefficients",
         "children": [
          {
           "t": "check",
           "name": "pearson",
           "label": "Pearson"
          },
          {
           "t": "check",
           "name": "spearman",
           "label": "Spearman"
          },
          {
           "t": "check",
           "name": "kendall"
          }
         ]
        }
       ]
      },
      {
       "col": 1,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Additional Options",
         "children": [
          {
           "t": "check",
           "name": "sig"
          },
          {
           "t": "check",
           "name": "flag"
          },
          {
           "t": "check",
           "name": "n"
          },
          {
           "t": "check",
           "name": "ci",
           "label": "Confidence intervals",
           "children": [
            {
             "t": "text",
             "name": "ciWidth",
             "label": "Interval",
             "format": "number",
             "enable": "ci"
            }
           ]
          }
         ]
        }
       ]
      },
      {
       "col": 0,
       "row": 1,
       "children": [
        {
         "t": "label",
         "label": "Hypothesis",
         "children": [
          {
           "t": "radio",
           "option": "hypothesis",
           "part": "corr",
           "label": "corr"
          },
          {
           "t": "radio",
           "option": "hypothesis",
           "part": "pos",
           "label": "pos"
          },
          {
           "t": "radio",
           "option": "hypothesis",
           "part": "neg",
           "label": "neg"
          }
         ]
        }
       ]
      },
      {
       "col": 1,
       "row": 1,
       "children": [
        {
         "t": "label",
         "label": "Plot",
         "children": [
          {
           "t": "check",
           "name": "plots",
           "label": "Correlation matrix",
           "children": [
            {
             "t": "check",
             "name": "plotDens",
             "enable": "plots"
            },
            {
             "t": "check",
             "name": "plotStats",
             "enable": "plots"
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    }
   ]
  }
 },
 "corrPart": {
  "name": "corrPart",
  "ns": "jmv",
  "title": "Partial Correlation",
  "menuGroup": "Regression",
  "menuSubgroup": "",
  "menuTitle": "Partial Correlation",
  "menuSubtitle": "",
  "options": [
   {
    "name": "vars",
    "type": "Variables",
    "title": "Variables",
    "default": null,
    "suggested": [
     "continuous",
     "ordinal"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "controls",
    "type": "Variables",
    "title": "Control variables",
    "default": null,
    "suggested": [
     "continuous",
     "ordinal"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "pearson",
    "type": "Bool",
    "title": "Pearson",
    "default": true
   },
   {
    "name": "spearman",
    "type": "Bool",
    "title": "Spearman",
    "default": false
   },
   {
    "name": "kendall",
    "type": "Bool",
    "title": "Kendall's tau-b",
    "default": false
   },
   {
    "name": "type",
    "type": "List",
    "title": "Correlation type",
    "default": "part",
    "choices": [
     {
      "value": "part",
      "title": "Partial"
     },
     {
      "value": "semi",
      "title": "Semipartial"
     }
    ]
   },
   {
    "name": "sig",
    "type": "Bool",
    "title": "Report significance",
    "default": true
   },
   {
    "name": "flag",
    "type": "Bool",
    "title": "Flag significant correlations",
    "default": false
   },
   {
    "name": "n",
    "type": "Bool",
    "title": "N",
    "default": false
   },
   {
    "name": "hypothesis",
    "type": "List",
    "title": "Hypothesis",
    "default": "corr",
    "choices": [
     {
      "value": "corr",
      "title": "Correlated"
     },
     {
      "value": "pos",
      "title": "Correlated positively"
     },
     {
      "value": "neg",
      "title": "Correlated negatively"
     }
    ]
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "vars"
      },
      {
       "name": "controls"
      }
     ]
    },
    {
     "t": "grid",
     "cells": [
      {
       "col": 0,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Correlation Coefficients",
         "children": [
          {
           "t": "check",
           "name": "pearson",
           "label": "Pearson"
          },
          {
           "t": "check",
           "name": "spearman",
           "label": "Spearman"
          },
          {
           "t": "check",
           "name": "kendall"
          }
         ]
        }
       ]
      },
      {
       "col": 1,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Correlation Type",
         "children": [
          {
           "t": "radio",
           "option": "type",
           "part": "part",
           "label": "part"
          },
          {
           "t": "radio",
           "option": "type",
           "part": "semi",
           "label": "semi"
          }
         ]
        }
       ]
      },
      {
       "col": 0,
       "row": 1,
       "children": [
        {
         "t": "label",
         "label": "Hypothesis",
         "children": [
          {
           "t": "radio",
           "option": "hypothesis",
           "part": "corr",
           "label": "corr"
          },
          {
           "t": "radio",
           "option": "hypothesis",
           "part": "pos",
           "label": "pos"
          },
          {
           "t": "radio",
           "option": "hypothesis",
           "part": "neg",
           "label": "neg"
          }
         ]
        }
       ]
      },
      {
       "col": 1,
       "row": 1,
       "children": [
        {
         "t": "label",
         "label": "Additional Options",
         "children": [
          {
           "t": "check",
           "name": "sig"
          },
          {
           "t": "check",
           "name": "flag"
          },
          {
           "t": "check",
           "name": "n"
          }
         ]
        }
       ]
      }
     ]
    }
   ]
  }
 },
 "linReg": {
  "name": "linReg",
  "ns": "jmv",
  "title": "Linear Regression",
  "menuGroup": "Regression",
  "menuSubgroup": "",
  "menuTitle": "Linear Regression",
  "menuSubtitle": "",
  "options": [
   {
    "name": "dep",
    "type": "Variable",
    "title": "Dependent Variable",
    "default": null,
    "suggested": [
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "covs",
    "type": "Variables",
    "title": "Covariates",
    "default": null,
    "suggested": [
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "factors",
    "type": "Variables",
    "title": "Factors",
    "default": null,
    "suggested": [
     "nominal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "weights",
    "type": "Variable",
    "title": "Weights (optional)",
    "default": null,
    "suggested": [
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "blocks",
    "type": "Array",
    "title": "Blocks",
    "default": [
     []
    ]
   },
   {
    "name": "refLevels",
    "type": "Array",
    "title": "Reference Levels",
    "default": null
   },
   {
    "name": "intercept",
    "type": "List",
    "title": "Intercept",
    "default": "refLevel",
    "choices": [
     {
      "value": "refLevel",
      "title": "refLevel"
     },
     {
      "value": "grandMean",
      "title": "grandMean"
     }
    ]
   },
   {
    "name": "r",
    "type": "Bool",
    "title": "R",
    "default": true
   },
   {
    "name": "r2",
    "type": "Bool",
    "title": "R²",
    "default": true
   },
   {
    "name": "r2Adj",
    "type": "Bool",
    "title": "Adjusted R²",
    "default": false
   },
   {
    "name": "aic",
    "type": "Bool",
    "title": "AIC",
    "default": false
   },
   {
    "name": "bic",
    "type": "Bool",
    "title": "BIC",
    "default": false
   },
   {
    "name": "rmse",
    "type": "Bool",
    "title": "RMSE",
    "default": false
   },
   {
    "name": "modelTest",
    "type": "Bool",
    "title": "F test",
    "default": false
   },
   {
    "name": "anova",
    "type": "Bool",
    "title": "ANOVA test",
    "default": false
   },
   {
    "name": "ci",
    "type": "Bool",
    "title": "Confidence interval",
    "default": false
   },
   {
    "name": "ciWidth",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "stdEst",
    "type": "Bool",
    "title": "Standardized estimate",
    "default": false
   },
   {
    "name": "ciStdEst",
    "type": "Bool",
    "title": "Confidence interval",
    "default": false
   },
   {
    "name": "ciWidthStdEst",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "norm",
    "type": "Bool",
    "title": "Normality test",
    "default": false
   },
   {
    "name": "qqPlot",
    "type": "Bool",
    "title": "Q-Q plot of residuals",
    "default": false
   },
   {
    "name": "resPlots",
    "type": "Bool",
    "title": "Residual plots",
    "default": false
   },
   {
    "name": "durbin",
    "type": "Bool",
    "title": "Autocorrelation test",
    "default": false
   },
   {
    "name": "collin",
    "type": "Bool",
    "title": "Collinearity statistics",
    "default": false
   },
   {
    "name": "cooks",
    "type": "Bool",
    "title": "Cook's distance",
    "default": false
   },
   {
    "name": "mahal",
    "type": "Bool",
    "title": "Mahalanobis distance",
    "default": false
   },
   {
    "name": "mahalp",
    "type": "List",
    "title": "mahalp",
    "default": "0.001",
    "choices": [
     {
      "value": "0.05",
      "title": "0.05"
     },
     {
      "value": "0.01",
      "title": "0.01"
     },
     {
      "value": "0.001",
      "title": "0.001"
     }
    ]
   },
   {
    "name": "emMeans",
    "type": "Array",
    "title": "Marginal Means",
    "default": [
     []
    ]
   },
   {
    "name": "ciEmm",
    "type": "Bool",
    "title": "Confidence interval",
    "default": true
   },
   {
    "name": "ciWidthEmm",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "emmPlots",
    "type": "Bool",
    "title": "Marginal means plots",
    "default": true
   },
   {
    "name": "emmTables",
    "type": "Bool",
    "title": "Marginal means tables",
    "default": false
   },
   {
    "name": "emmWeights",
    "type": "Bool",
    "title": "Equal cell weights",
    "default": true
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "dep",
       "max": 1
      },
      {
       "name": "covs"
      },
      {
       "name": "factors"
      },
      {
       "name": "weights",
       "max": 1
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Reference Levels",
     "collapsed": true,
     "children": [
      {
       "t": "label",
       "label": "Intercept",
       "children": [
        {
         "t": "radio",
         "option": "intercept",
         "part": "refLevel",
         "label": "Reference level (dummy coding)"
        },
        {
         "t": "radio",
         "option": "intercept",
         "part": "grandMean",
         "label": "Grand mean (simple coding)"
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Assumption Checks",
     "collapsed": true,
     "children": [
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Assumption Checks",
           "children": [
            {
             "t": "check",
             "name": "durbin"
            },
            {
             "t": "check",
             "name": "collin"
            },
            {
             "t": "check",
             "name": "norm"
            },
            {
             "t": "check",
             "name": "qqPlot"
            },
            {
             "t": "check",
             "name": "resPlots"
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Data Summary",
           "children": [
            {
             "t": "check",
             "name": "cooks"
            },
            {
             "t": "check",
             "name": "mahal",
             "children": [
              {
               "t": "combo",
               "name": "mahalp",
               "label": "p < ",
               "enable": "mahal"
              }
             ]
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Model Fit",
     "collapsed": true,
     "children": [
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Fit Measures",
           "children": [
            {
             "t": "check",
             "name": "r"
            },
            {
             "t": "check",
             "name": "r2"
            },
            {
             "t": "check",
             "name": "r2Adj"
            },
            {
             "t": "check",
             "name": "aic"
            },
            {
             "t": "check",
             "name": "bic"
            },
            {
             "t": "check",
             "name": "rmse"
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Overall Model Test",
           "children": [
            {
             "t": "check",
             "name": "modelTest"
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Model Coefficients",
     "collapsed": true,
     "children": [
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Omnibus Test",
           "children": [
            {
             "t": "check",
             "name": "anova"
            }
           ]
          },
          {
           "t": "label",
           "label": "Estimate",
           "children": [
            {
             "t": "check",
             "name": "ci",
             "children": [
              {
               "t": "text",
               "name": "ciWidth",
               "label": "Interval",
               "format": "number",
               "enable": "ci"
              }
             ]
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Standardized Estimate",
           "children": [
            {
             "t": "check",
             "name": "stdEst"
            },
            {
             "t": "check",
             "name": "ciStdEst",
             "children": [
              {
               "t": "text",
               "name": "ciWidthStdEst",
               "label": "Interval",
               "format": "number",
               "enable": "ciStdEst"
              }
             ],
             "enable": "stdEst"
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Estimated Marginal Means",
     "collapsed": true,
     "children": [
      {
       "t": "supplier",
       "targets": []
      },
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "General Options",
           "children": [
            {
             "t": "check",
             "name": "emmWeights"
            },
            {
             "t": "check",
             "name": "ciEmm",
             "children": [
              {
               "t": "text",
               "name": "ciWidthEmm",
               "label": "Interval",
               "format": "number",
               "enable": "ciEmm"
              }
             ]
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Output",
           "children": [
            {
             "t": "check",
             "name": "emmPlots"
            },
            {
             "t": "check",
             "name": "emmTables"
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    }
   ]
  }
 },
 "logRegBin": {
  "name": "logRegBin",
  "ns": "jmv",
  "title": "Binomial Logistic Regression",
  "menuGroup": "Regression",
  "menuSubgroup": "Logistic Regression",
  "menuTitle": "2 Outcomes",
  "menuSubtitle": "Binomial",
  "options": [
   {
    "name": "dep",
    "type": "Variable",
    "title": "Dependent Variable",
    "default": null,
    "suggested": [
     "nominal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "covs",
    "type": "Variables",
    "title": "Covariates",
    "default": null,
    "suggested": [
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "factors",
    "type": "Variables",
    "title": "Factors",
    "default": null,
    "suggested": [
     "nominal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "blocks",
    "type": "Array",
    "title": "Blocks",
    "default": [
     []
    ]
   },
   {
    "name": "refLevels",
    "type": "Array",
    "title": "Reference Levels",
    "default": null
   },
   {
    "name": "modelTest",
    "type": "Bool",
    "title": "Overall model test",
    "default": false
   },
   {
    "name": "dev",
    "type": "Bool",
    "title": "Deviance",
    "default": true
   },
   {
    "name": "aic",
    "type": "Bool",
    "title": "AIC",
    "default": true
   },
   {
    "name": "bic",
    "type": "Bool",
    "title": "BIC",
    "default": false
   },
   {
    "name": "pseudoR2",
    "type": "NMXList",
    "title": "Pseudo R²",
    "default": [
     "r2mf"
    ],
    "choices": [
     {
      "value": "r2mf",
      "title": "McFadden's R²"
     },
     {
      "value": "r2cs",
      "title": "Cox & Snell's R²"
     },
     {
      "value": "r2n",
      "title": "Nagelkerke's R²"
     },
     {
      "value": "r2t",
      "title": "Tjur's R²"
     }
    ]
   },
   {
    "name": "omni",
    "type": "Bool",
    "title": "Likelihood ratio tests",
    "default": false
   },
   {
    "name": "ci",
    "type": "Bool",
    "title": "Confidence interval",
    "default": false
   },
   {
    "name": "ciWidth",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "OR",
    "type": "Bool",
    "title": "Odds ratio",
    "default": false
   },
   {
    "name": "ciOR",
    "type": "Bool",
    "title": "Confidence interval",
    "default": false
   },
   {
    "name": "ciWidthOR",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "emMeans",
    "type": "Array",
    "title": "Marginal Means",
    "default": [
     []
    ]
   },
   {
    "name": "ciEmm",
    "type": "Bool",
    "title": "Confidence interval",
    "default": true
   },
   {
    "name": "ciWidthEmm",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "emmPlots",
    "type": "Bool",
    "title": "Marginal means plots",
    "default": true
   },
   {
    "name": "emmTables",
    "type": "Bool",
    "title": "Marginal means tables",
    "default": false
   },
   {
    "name": "emmWeights",
    "type": "Bool",
    "title": "Equal cell weights",
    "default": true
   },
   {
    "name": "class",
    "type": "Bool",
    "title": "Classification table",
    "default": false
   },
   {
    "name": "acc",
    "type": "Bool",
    "title": "Accuracy",
    "default": false
   },
   {
    "name": "spec",
    "type": "Bool",
    "title": "Specificity",
    "default": false
   },
   {
    "name": "sens",
    "type": "Bool",
    "title": "Sensitivity",
    "default": false
   },
   {
    "name": "auc",
    "type": "Bool",
    "title": "AUC",
    "default": false
   },
   {
    "name": "rocPlot",
    "type": "Bool",
    "title": "ROC curve",
    "default": false
   },
   {
    "name": "cutOff",
    "type": "Number",
    "title": "Cut-off value",
    "default": 0.5,
    "min": 0,
    "max": 1
   },
   {
    "name": "cutOffPlot",
    "type": "Bool",
    "title": "Cut-off plot",
    "default": false
   },
   {
    "name": "collin",
    "type": "Bool",
    "title": "Collinearity statistics",
    "default": false
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "dep",
       "max": 1
      },
      {
       "name": "covs"
      },
      {
       "name": "factors"
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Assumption Checks",
     "collapsed": true,
     "children": [
      {
       "t": "check",
       "name": "collin"
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Model Fit",
     "collapsed": true,
     "children": [
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Fit Measures",
           "children": [
            {
             "t": "check",
             "name": "dev"
            },
            {
             "t": "check",
             "name": "aic"
            },
            {
             "t": "check",
             "name": "bic"
            },
            {
             "t": "check",
             "name": "modelTest"
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Pseudo R²",
           "children": [
            {
             "t": "checkpart",
             "option": "pseudoR2",
             "part": "r2mf",
             "label": "r2mf"
            },
            {
             "t": "checkpart",
             "option": "pseudoR2",
             "part": "r2cs",
             "label": "r2cs"
            },
            {
             "t": "checkpart",
             "option": "pseudoR2",
             "part": "r2n",
             "label": "r2n"
            },
            {
             "t": "checkpart",
             "option": "pseudoR2",
             "part": "r2t",
             "label": "r2t"
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Model Coefficients",
     "collapsed": true,
     "children": [
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Omnibus Tests",
           "children": [
            {
             "t": "check",
             "name": "omni"
            }
           ]
          },
          {
           "t": "label",
           "label": "Estimate (Log Odds Ratio)",
           "children": [
            {
             "t": "check",
             "name": "ci",
             "children": [
              {
               "t": "text",
               "name": "ciWidth",
               "label": "Interval",
               "format": "number",
               "enable": "ci"
              }
             ]
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Odds Ratio",
           "children": [
            {
             "t": "check",
             "name": "OR"
            },
            {
             "t": "check",
             "name": "ciOR",
             "children": [
              {
               "t": "text",
               "name": "ciWidthOR",
               "label": "Interval",
               "format": "number",
               "enable": "ciOR"
              }
             ],
             "enable": "OR"
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Estimated Marginal Means",
     "collapsed": true,
     "children": [
      {
       "t": "supplier",
       "targets": []
      },
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "General Options",
           "children": [
            {
             "t": "check",
             "name": "emmWeights"
            },
            {
             "t": "check",
             "name": "ciEmm",
             "children": [
              {
               "t": "text",
               "name": "ciWidthEmm",
               "label": "Interval",
               "format": "number",
               "enable": "ciEmm"
              }
             ]
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Output",
           "children": [
            {
             "t": "check",
             "name": "emmPlots"
            },
            {
             "t": "check",
             "name": "emmTables"
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Prediction",
     "collapsed": true,
     "children": [
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Cut-Off",
           "children": [
            {
             "t": "check",
             "name": "cutOffPlot"
            },
            {
             "t": "text",
             "name": "cutOff",
             "label": "",
             "format": "number"
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Predictive Measures",
           "children": [
            {
             "t": "check",
             "name": "class"
            },
            {
             "t": "check",
             "name": "acc"
            },
            {
             "t": "check",
             "name": "spec"
            },
            {
             "t": "check",
             "name": "sens"
            }
           ]
          }
         ]
        },
        {
         "col": 2,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "ROC",
           "children": [
            {
             "t": "check",
             "name": "rocPlot"
            },
            {
             "t": "check",
             "name": "auc"
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    }
   ]
  }
 },
 "logRegMulti": {
  "name": "logRegMulti",
  "ns": "jmv",
  "title": "Multinomial Logistic Regression",
  "menuGroup": "Regression",
  "menuSubgroup": "Logistic Regression",
  "menuTitle": "N Outcomes",
  "menuSubtitle": "Multinomial",
  "options": [
   {
    "name": "dep",
    "type": "Variable",
    "title": "Dependent Variable",
    "default": null,
    "suggested": [
     "nominal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "covs",
    "type": "Variables",
    "title": "Covariates",
    "default": null,
    "suggested": [
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "factors",
    "type": "Variables",
    "title": "Factors",
    "default": null,
    "suggested": [
     "nominal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "blocks",
    "type": "Array",
    "title": "Blocks",
    "default": [
     []
    ]
   },
   {
    "name": "refLevels",
    "type": "Array",
    "title": "Reference Levels",
    "default": null
   },
   {
    "name": "modelTest",
    "type": "Bool",
    "title": "Overall model test",
    "default": false
   },
   {
    "name": "dev",
    "type": "Bool",
    "title": "Deviance",
    "default": true
   },
   {
    "name": "aic",
    "type": "Bool",
    "title": "AIC",
    "default": true
   },
   {
    "name": "bic",
    "type": "Bool",
    "title": "BIC",
    "default": false
   },
   {
    "name": "pseudoR2",
    "type": "NMXList",
    "title": "Pseudo R²",
    "default": [
     "r2mf"
    ],
    "choices": [
     {
      "value": "r2mf",
      "title": "McFadden's R²"
     },
     {
      "value": "r2cs",
      "title": "Cox & Snell's R²"
     },
     {
      "value": "r2n",
      "title": "Nagelkerke's R²"
     }
    ]
   },
   {
    "name": "omni",
    "type": "Bool",
    "title": "Likelihood ratio tests",
    "default": false
   },
   {
    "name": "ci",
    "type": "Bool",
    "title": "Confidence interval",
    "default": false
   },
   {
    "name": "ciWidth",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "OR",
    "type": "Bool",
    "title": "Odds ratio",
    "default": false
   },
   {
    "name": "ciOR",
    "type": "Bool",
    "title": "Confidence interval",
    "default": false
   },
   {
    "name": "ciWidthOR",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "emMeans",
    "type": "Array",
    "title": "Marginal Means",
    "default": [
     []
    ]
   },
   {
    "name": "ciEmm",
    "type": "Bool",
    "title": "Confidence interval",
    "default": true
   },
   {
    "name": "ciWidthEmm",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "emmPlots",
    "type": "Bool",
    "title": "Marginal means plots",
    "default": true
   },
   {
    "name": "emmTables",
    "type": "Bool",
    "title": "Marginal means tables",
    "default": false
   },
   {
    "name": "emmWeights",
    "type": "Bool",
    "title": "Equal cell weights",
    "default": true
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "dep",
       "max": 1
      },
      {
       "name": "covs"
      },
      {
       "name": "factors"
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Model Fit",
     "collapsed": true,
     "children": [
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Fit Measures",
           "children": [
            {
             "t": "check",
             "name": "dev"
            },
            {
             "t": "check",
             "name": "aic"
            },
            {
             "t": "check",
             "name": "bic"
            },
            {
             "t": "check",
             "name": "modelTest"
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Pseudo R²",
           "children": [
            {
             "t": "checkpart",
             "option": "pseudoR2",
             "part": "r2mf",
             "label": "r2mf"
            },
            {
             "t": "checkpart",
             "option": "pseudoR2",
             "part": "r2cs",
             "label": "r2cs"
            },
            {
             "t": "checkpart",
             "option": "pseudoR2",
             "part": "r2n",
             "label": "r2n"
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Model Coefficients",
     "collapsed": true,
     "children": [
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Omnibus Tests",
           "children": [
            {
             "t": "check",
             "name": "omni"
            }
           ]
          },
          {
           "t": "label",
           "label": "Estimate (Log Odds Ratio)",
           "children": [
            {
             "t": "check",
             "name": "ci",
             "children": [
              {
               "t": "text",
               "name": "ciWidth",
               "label": "Interval",
               "format": "number",
               "enable": "ci"
              }
             ]
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Odds Ratio",
           "children": [
            {
             "t": "check",
             "name": "OR"
            },
            {
             "t": "check",
             "name": "ciOR",
             "children": [
              {
               "t": "text",
               "name": "ciWidthOR",
               "label": "Interval",
               "format": "number",
               "enable": "ciOR"
              }
             ],
             "enable": "OR"
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Estimated Marginal Means",
     "collapsed": true,
     "children": [
      {
       "t": "supplier",
       "targets": []
      },
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "General Options",
           "children": [
            {
             "t": "check",
             "name": "emmWeights"
            },
            {
             "t": "check",
             "name": "ciEmm",
             "children": [
              {
               "t": "text",
               "name": "ciWidthEmm",
               "label": "Interval",
               "format": "number",
               "enable": "ciEmm"
              }
             ]
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Output",
           "children": [
            {
             "t": "check",
             "name": "emmPlots"
            },
            {
             "t": "check",
             "name": "emmTables"
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    }
   ]
  }
 },
 "logRegOrd": {
  "name": "logRegOrd",
  "ns": "jmv",
  "title": "Ordinal Logistic Regression",
  "menuGroup": "Regression",
  "menuSubgroup": "Logistic Regression",
  "menuTitle": "Ordinal Outcomes",
  "menuSubtitle": "",
  "options": [
   {
    "name": "dep",
    "type": "Variable",
    "title": "Dependent Variable",
    "default": null,
    "suggested": [
     "ordinal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "covs",
    "type": "Variables",
    "title": "Covariates",
    "default": null,
    "suggested": [
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "factors",
    "type": "Variables",
    "title": "Factors",
    "default": null,
    "suggested": [
     "nominal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "blocks",
    "type": "Array",
    "title": "Blocks",
    "default": [
     []
    ]
   },
   {
    "name": "refLevels",
    "type": "Array",
    "title": "Reference Levels",
    "default": null
   },
   {
    "name": "modelTest",
    "type": "Bool",
    "title": "Overall model test",
    "default": false
   },
   {
    "name": "dev",
    "type": "Bool",
    "title": "Deviance",
    "default": true
   },
   {
    "name": "aic",
    "type": "Bool",
    "title": "AIC",
    "default": true
   },
   {
    "name": "bic",
    "type": "Bool",
    "title": "BIC",
    "default": false
   },
   {
    "name": "pseudoR2",
    "type": "NMXList",
    "title": "Pseudo R²",
    "default": [
     "r2mf"
    ],
    "choices": [
     {
      "value": "r2mf",
      "title": "McFadden's R²"
     },
     {
      "value": "r2cs",
      "title": "Cox & Snell's R²"
     },
     {
      "value": "r2n",
      "title": "Nagelkerke's R²"
     }
    ]
   },
   {
    "name": "omni",
    "type": "Bool",
    "title": "Likelihood ratio tests",
    "default": false
   },
   {
    "name": "thres",
    "type": "Bool",
    "title": "Model thresholds",
    "default": false
   },
   {
    "name": "ci",
    "type": "Bool",
    "title": "Confidence interval",
    "default": false
   },
   {
    "name": "ciWidth",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "OR",
    "type": "Bool",
    "title": "Odds ratio",
    "default": false
   },
   {
    "name": "ciOR",
    "type": "Bool",
    "title": "Confidence interval",
    "default": false
   },
   {
    "name": "ciWidthOR",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "dep",
       "max": 1
      },
      {
       "name": "covs"
      },
      {
       "name": "factors"
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Model Fit",
     "collapsed": true,
     "children": [
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Fit Measures",
           "children": [
            {
             "t": "check",
             "name": "dev"
            },
            {
             "t": "check",
             "name": "aic"
            },
            {
             "t": "check",
             "name": "bic"
            },
            {
             "t": "check",
             "name": "modelTest"
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Pseudo R²",
           "children": [
            {
             "t": "checkpart",
             "option": "pseudoR2",
             "part": "r2mf",
             "label": "r2mf"
            },
            {
             "t": "checkpart",
             "option": "pseudoR2",
             "part": "r2cs",
             "label": "r2cs"
            },
            {
             "t": "checkpart",
             "option": "pseudoR2",
             "part": "r2n",
             "label": "r2n"
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Model Coefficients",
     "collapsed": true,
     "children": [
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Omnibus Tests",
           "children": [
            {
             "t": "check",
             "name": "omni"
            }
           ]
          },
          {
           "t": "label",
           "label": "Thresholds",
           "children": [
            {
             "t": "check",
             "name": "thres"
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Estimate (Log Odds Ratio)",
           "children": [
            {
             "t": "check",
             "name": "ci",
             "children": [
              {
               "t": "text",
               "name": "ciWidth",
               "label": "Interval",
               "format": "number",
               "enable": "ci"
              }
             ]
            }
           ]
          },
          {
           "t": "label",
           "label": "Odds Ratio",
           "children": [
            {
             "t": "check",
             "name": "OR"
            },
            {
             "t": "check",
             "name": "ciOR",
             "children": [
              {
               "t": "text",
               "name": "ciWidthOR",
               "label": "Interval",
               "format": "number",
               "enable": "ciOR"
              }
             ],
             "enable": "OR"
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    }
   ]
  }
 },
 "propTestN": {
  "name": "propTestN",
  "ns": "jmv",
  "title": "Proportion Test (N Outcomes)",
  "menuGroup": "Frequencies",
  "menuSubgroup": "One Sample Proportion Tests",
  "menuTitle": "N Outcomes",
  "menuSubtitle": "χ² Goodness of fit",
  "options": [
   {
    "name": "var",
    "type": "Variable",
    "title": "Variable",
    "default": null,
    "suggested": [
     "nominal",
     "ordinal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "counts",
    "type": "Variable",
    "title": "Counts (optional)",
    "default": null,
    "suggested": [],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "expected",
    "type": "Bool",
    "title": "Expected counts",
    "default": false
   },
   {
    "name": "ratio",
    "type": "Array",
    "title": "Expected Proportions",
    "default": null
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "var",
       "max": 1
      },
      {
       "name": "counts",
       "max": 1
      }
     ]
    },
    {
     "t": "check",
     "name": "expected"
    }
   ]
  }
 },
 "contTables": {
  "name": "contTables",
  "ns": "jmv",
  "title": "Contingency Tables",
  "menuGroup": "Frequencies",
  "menuSubgroup": "Contingency Tables",
  "menuTitle": "Independent Samples",
  "menuSubtitle": "χ² test of association",
  "options": [
   {
    "name": "rows",
    "type": "Variable",
    "title": "Rows",
    "default": null,
    "suggested": [
     "nominal",
     "ordinal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "cols",
    "type": "Variable",
    "title": "Columns",
    "default": null,
    "suggested": [
     "nominal",
     "ordinal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "counts",
    "type": "Variable",
    "title": "Counts (optional)",
    "default": null,
    "suggested": [
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "layers",
    "type": "Variables",
    "title": "Layers",
    "default": null,
    "suggested": [],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "chiSq",
    "type": "Bool",
    "title": "χ²",
    "default": true
   },
   {
    "name": "chiSqCorr",
    "type": "Bool",
    "title": "χ² continuity correction",
    "default": false
   },
   {
    "name": "zProp",
    "type": "Bool",
    "title": "z test for difference in 2 proportions",
    "default": false
   },
   {
    "name": "likeRat",
    "type": "Bool",
    "title": "Likelihood ratio",
    "default": false
   },
   {
    "name": "fisher",
    "type": "Bool",
    "title": "Fisher's exact test",
    "default": false
   },
   {
    "name": "contCoef",
    "type": "Bool",
    "title": "Contingency coefficient",
    "default": false
   },
   {
    "name": "phiCra",
    "type": "Bool",
    "title": "Phi and Cramer's V",
    "default": false
   },
   {
    "name": "diffProp",
    "type": "Bool",
    "title": "Difference in proportions",
    "default": false
   },
   {
    "name": "logOdds",
    "type": "Bool",
    "title": "Log odds ratio",
    "default": false
   },
   {
    "name": "odds",
    "type": "Bool",
    "title": "Odds ratio",
    "default": false
   },
   {
    "name": "relRisk",
    "type": "Bool",
    "title": "Relative risk",
    "default": false
   },
   {
    "name": "ci",
    "type": "Bool",
    "title": "Confidence intervals",
    "default": true
   },
   {
    "name": "ciWidth",
    "type": "Number",
    "title": "Interval",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "compare",
    "type": "List",
    "title": "Compare",
    "default": "rows",
    "choices": [
     {
      "value": "rows",
      "title": "rows"
     },
     {
      "value": "columns",
      "title": "columns"
     }
    ]
   },
   {
    "name": "hypothesis",
    "type": "List",
    "title": "Alternative hypothesis",
    "default": "different",
    "choices": [
     {
      "value": "different",
      "title": "Group 1 ≠ Group 2"
     },
     {
      "value": "oneGreater",
      "title": "Group 1 > Group 2"
     },
     {
      "value": "twoGreater",
      "title": "Group 1 < Group 2"
     }
    ]
   },
   {
    "name": "gamma",
    "type": "Bool",
    "title": "Gamma",
    "default": false
   },
   {
    "name": "taub",
    "type": "Bool",
    "title": "Kendall's tau-b",
    "default": false
   },
   {
    "name": "mh",
    "type": "Bool",
    "title": "Mantel-Haenszel",
    "default": false
   },
   {
    "name": "obs",
    "type": "Bool",
    "title": "Observed counts",
    "default": true
   },
   {
    "name": "exp",
    "type": "Bool",
    "title": "Expected counts",
    "default": false
   },
   {
    "name": "pcRow",
    "type": "Bool",
    "title": "Row",
    "default": false
   },
   {
    "name": "pcCol",
    "type": "Bool",
    "title": "Column",
    "default": false
   },
   {
    "name": "pcTot",
    "type": "Bool",
    "title": "Total",
    "default": false
   },
   {
    "name": "barplot",
    "type": "Bool",
    "title": "Bar Plot",
    "default": false
   },
   {
    "name": "yaxis",
    "type": "List",
    "title": "Y-axis",
    "default": "ycounts",
    "choices": [
     {
      "value": "ycounts",
      "title": "Counts"
     },
     {
      "value": "ypc",
      "title": "Percentages"
     }
    ]
   },
   {
    "name": "yaxisPc",
    "type": "List",
    "title": "yaxisPc",
    "default": "total_pc",
    "choices": [
     {
      "value": "total_pc",
      "title": "of total"
     },
     {
      "value": "column_pc",
      "title": "within column"
     },
     {
      "value": "row_pc",
      "title": "within rows"
     }
    ]
   },
   {
    "name": "xaxis",
    "type": "List",
    "title": "X-axis",
    "default": "xrows",
    "choices": [
     {
      "value": "xrows",
      "title": "Rows"
     },
     {
      "value": "xcols",
      "title": "Columns"
     }
    ]
   },
   {
    "name": "bartype",
    "type": "List",
    "title": "Bar Type",
    "default": "dodge",
    "choices": [
     {
      "value": "dodge",
      "title": "Side by side"
     },
     {
      "value": "stack",
      "title": "Stacked"
     }
    ]
   },
   {
    "name": "resU",
    "type": "Bool",
    "title": "Unstandardized residuals",
    "default": false
   },
   {
    "name": "resP",
    "type": "Bool",
    "title": "Pearson residuals",
    "default": false
   },
   {
    "name": "hlresP",
    "type": "Number",
    "title": "Highlight values above",
    "default": 2
   },
   {
    "name": "resS",
    "type": "Bool",
    "title": "Standardized residuals (adjusted Pearson)",
    "default": false
   },
   {
    "name": "hlresS",
    "type": "Number",
    "title": "Highlight values above",
    "default": 2
   },
   {
    "name": "resA",
    "type": "Bool",
    "title": "Deviance residuals (Poisson GLM)",
    "default": false
   },
   {
    "name": "hlresA",
    "type": "Number",
    "title": "Highlight values above",
    "default": 2
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "rows",
       "max": 1
      },
      {
       "name": "cols",
       "max": 1
      },
      {
       "name": "counts",
       "max": 1
      },
      {
       "name": "layers"
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Statistics",
     "collapsed": true,
     "children": [
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "grid",
           "cells": [
            {
             "col": 0,
             "row": 0,
             "children": [
              {
               "t": "label",
               "label": "Tests",
               "children": [
                {
                 "t": "check",
                 "name": "chiSq"
                },
                {
                 "t": "check",
                 "name": "chiSqCorr"
                },
                {
                 "t": "check",
                 "name": "likeRat"
                },
                {
                 "t": "check",
                 "name": "fisher"
                },
                {
                 "t": "check",
                 "name": "zProp"
                }
               ]
              }
             ]
            }
           ]
          },
          {
           "t": "label",
           "label": "Hypothesis",
           "children": [
            {
             "t": "radio",
             "option": "hypothesis",
             "part": "different",
             "label": "Group 1 ≠ Group 2"
            },
            {
             "t": "radio",
             "option": "hypothesis",
             "part": "oneGreater",
             "label": "Group 1 > Group 2"
            },
            {
             "t": "radio",
             "option": "hypothesis",
             "part": "twoGreater",
             "label": "Group 1 < Group 2"
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Comparative Measures (2x2 only)",
           "children": [
            {
             "t": "check",
             "name": "odds"
            },
            {
             "t": "check",
             "name": "logOdds"
            },
            {
             "t": "check",
             "name": "relRisk"
            },
            {
             "t": "check",
             "name": "diffProp"
            },
            {
             "t": "check",
             "name": "ci",
             "children": [
              {
               "t": "text",
               "name": "ciWidth",
               "label": "",
               "format": "number",
               "enable": "ci"
              }
             ]
            },
            {
             "t": "combo",
             "name": "compare",
             "label": ""
            }
           ]
          }
         ]
        }
       ]
      },
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "grid",
           "cells": [
            {
             "col": 0,
             "row": 1,
             "children": [
              {
               "t": "label",
               "label": "Nominal",
               "children": [
                {
                 "t": "check",
                 "name": "contCoef"
                },
                {
                 "t": "check",
                 "name": "phiCra"
                }
               ]
              }
             ]
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "grid",
           "cells": [
            {
             "col": 1,
             "row": 1,
             "children": [
              {
               "t": "label",
               "label": "Ordinal",
               "children": [
                {
                 "t": "check",
                 "name": "gamma"
                },
                {
                 "t": "check",
                 "name": "taub"
                },
                {
                 "t": "check",
                 "name": "mh"
                }
               ]
              }
             ]
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Cells",
     "collapsed": true,
     "children": [
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Counts",
           "children": [
            {
             "t": "check",
             "name": "obs"
            },
            {
             "t": "check",
             "name": "exp"
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "grid",
           "cells": [
            {
             "col": 1,
             "row": 0,
             "children": [
              {
               "t": "label",
               "label": "Percentages",
               "children": [
                {
                 "t": "check",
                 "name": "pcRow"
                },
                {
                 "t": "check",
                 "name": "pcCol"
                },
                {
                 "t": "check",
                 "name": "pcTot"
                }
               ]
              }
             ]
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Post Hoc Tests",
     "collapsed": true,
     "children": [
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "grid",
           "cells": [
            {
             "col": 0,
             "row": 0,
             "children": [
              {
               "t": "label",
               "label": "Post Hoc Tests",
               "children": [
                {
                 "t": "check",
                 "name": "resU"
                },
                {
                 "t": "check",
                 "name": "resP",
                 "children": [
                  {
                   "t": "text",
                   "name": "hlresP",
                   "label": "",
                   "format": "number",
                   "enable": "resP"
                  }
                 ]
                },
                {
                 "t": "check",
                 "name": "resS",
                 "children": [
                  {
                   "t": "text",
                   "name": "hlresS",
                   "label": "",
                   "format": "number",
                   "enable": "resS"
                  }
                 ]
                },
                {
                 "t": "check",
                 "name": "resA",
                 "children": [
                  {
                   "t": "text",
                   "name": "hlresA",
                   "label": "",
                   "format": "number",
                   "enable": "resA"
                  }
                 ]
                }
               ]
              }
             ]
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Plots",
     "collapsed": true,
     "children": [
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Plots",
           "children": [
            {
             "t": "check",
             "name": "barplot"
            }
           ]
          },
          {
           "t": "label",
           "label": "Bar Type",
           "children": [
            {
             "t": "radio",
             "option": "bartype",
             "part": "dodge",
             "label": "dodge"
            },
            {
             "t": "radio",
             "option": "bartype",
             "part": "stack",
             "label": "stack"
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Y-Axis",
           "children": [
            {
             "t": "radio",
             "option": "yaxis",
             "part": "ycounts",
             "label": "ycounts"
            },
            {
             "t": "radio",
             "option": "yaxis",
             "part": "ypc",
             "label": "ypc"
            }
           ]
          },
          {
           "t": "label",
           "label": "X-Axis",
           "children": [
            {
             "t": "radio",
             "option": "xaxis",
             "part": "xrows",
             "label": "xrows"
            },
            {
             "t": "radio",
             "option": "xaxis",
             "part": "xcols",
             "label": "xcols"
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    }
   ]
  }
 },
 "contTablesPaired": {
  "name": "contTablesPaired",
  "ns": "jmv",
  "title": "Paired Samples Contingency Tables",
  "menuGroup": "Frequencies",
  "menuSubgroup": "Contingency Tables",
  "menuTitle": "Paired Samples",
  "menuSubtitle": "McNemar test",
  "options": [
   {
    "name": "rows",
    "type": "Variable",
    "title": "Rows",
    "default": null,
    "suggested": [
     "nominal",
     "ordinal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "cols",
    "type": "Variable",
    "title": "Columns",
    "default": null,
    "suggested": [
     "nominal",
     "ordinal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "counts",
    "type": "Variable",
    "title": "Counts (optional)",
    "default": null,
    "suggested": [
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "chiSq",
    "type": "Bool",
    "title": "χ²",
    "default": true
   },
   {
    "name": "chiSqCorr",
    "type": "Bool",
    "title": "χ² continuity correction",
    "default": false
   },
   {
    "name": "exact",
    "type": "Bool",
    "title": "Log odds ratio exact",
    "default": false
   },
   {
    "name": "pcRow",
    "type": "Bool",
    "title": "Row",
    "default": false
   },
   {
    "name": "pcCol",
    "type": "Bool",
    "title": "Column",
    "default": false
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "rows",
       "max": 1
      },
      {
       "name": "cols",
       "max": 1
      },
      {
       "name": "counts",
       "max": 1
      }
     ]
    },
    {
     "t": "check",
     "name": "chiSq"
    },
    {
     "t": "check",
     "name": "chiSqCorr"
    },
    {
     "t": "check",
     "name": "exact"
    },
    {
     "t": "grid",
     "cells": [
      {
       "col": 1,
       "row": 1,
       "children": [
        {
         "t": "label",
         "label": "Percentages",
         "children": [
          {
           "t": "check",
           "name": "pcRow"
          },
          {
           "t": "check",
           "name": "pcCol"
          }
         ]
        }
       ]
      }
     ]
    }
   ]
  }
 },
 "logLinear": {
  "name": "logLinear",
  "ns": "jmv",
  "title": "Log-Linear Regression",
  "menuGroup": "Frequencies",
  "menuSubgroup": "",
  "menuTitle": "Log-Linear Regression",
  "menuSubtitle": "",
  "options": [
   {
    "name": "factors",
    "type": "Variables",
    "title": "Factors",
    "default": null,
    "suggested": [
     "nominal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "counts",
    "type": "Variable",
    "title": "Counts (optional)",
    "default": null,
    "suggested": [],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "blocks",
    "type": "Array",
    "title": "Blocks",
    "default": [
     []
    ]
   },
   {
    "name": "refLevels",
    "type": "Array",
    "title": "Reference Levels",
    "default": null
   },
   {
    "name": "modelTest",
    "type": "Bool",
    "title": "Overall model test",
    "default": false
   },
   {
    "name": "dev",
    "type": "Bool",
    "title": "Deviance",
    "default": true
   },
   {
    "name": "aic",
    "type": "Bool",
    "title": "AIC",
    "default": true
   },
   {
    "name": "bic",
    "type": "Bool",
    "title": "BIC",
    "default": false
   },
   {
    "name": "pseudoR2",
    "type": "NMXList",
    "title": "Pseudo R²",
    "default": [
     "r2mf"
    ],
    "choices": [
     {
      "value": "r2mf",
      "title": "McFadden's R²"
     },
     {
      "value": "r2cs",
      "title": "Cox & Snell's R²"
     },
     {
      "value": "r2n",
      "title": "Nagelkerke's R²"
     }
    ]
   },
   {
    "name": "omni",
    "type": "Bool",
    "title": "Likelihood ratio tests",
    "default": false
   },
   {
    "name": "ci",
    "type": "Bool",
    "title": "Confidence interval",
    "default": false
   },
   {
    "name": "ciWidth",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "RR",
    "type": "Bool",
    "title": "Rate ratio",
    "default": false
   },
   {
    "name": "ciRR",
    "type": "Bool",
    "title": "Confidence interval",
    "default": false
   },
   {
    "name": "ciWidthRR",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "emMeans",
    "type": "Array",
    "title": "Marginal Means",
    "default": [
     []
    ]
   },
   {
    "name": "ciEmm",
    "type": "Bool",
    "title": "Confidence interval",
    "default": true
   },
   {
    "name": "ciWidthEmm",
    "type": "Number",
    "title": "Confidence level",
    "default": 95,
    "min": 50,
    "max": 99.9
   },
   {
    "name": "emmPlots",
    "type": "Bool",
    "title": "Marginal means plots",
    "default": true
   },
   {
    "name": "emmTables",
    "type": "Bool",
    "title": "Marginal means tables",
    "default": false
   },
   {
    "name": "emmWeights",
    "type": "Bool",
    "title": "Equal cell weights",
    "default": true
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "factors"
      },
      {
       "name": "counts",
       "max": 1
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Model Fit",
     "collapsed": true,
     "children": [
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Fit Measures",
           "children": [
            {
             "t": "check",
             "name": "dev"
            },
            {
             "t": "check",
             "name": "aic"
            },
            {
             "t": "check",
             "name": "bic"
            },
            {
             "t": "check",
             "name": "modelTest"
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Pseudo R²",
           "children": [
            {
             "t": "checkpart",
             "option": "pseudoR2",
             "part": "r2mf",
             "label": "r2mf"
            },
            {
             "t": "checkpart",
             "option": "pseudoR2",
             "part": "r2cs",
             "label": "r2cs"
            },
            {
             "t": "checkpart",
             "option": "pseudoR2",
             "part": "r2n",
             "label": "r2n"
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Model Coefficients",
     "collapsed": true,
     "children": [
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Omnibus Tests",
           "children": [
            {
             "t": "check",
             "name": "omni"
            }
           ]
          },
          {
           "t": "label",
           "label": "Estimate (Log Rate Ratio)",
           "children": [
            {
             "t": "check",
             "name": "ci",
             "children": [
              {
               "t": "text",
               "name": "ciWidth",
               "label": "Interval",
               "format": "number",
               "enable": "ci"
              }
             ]
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Rate Ratio",
           "children": [
            {
             "t": "check",
             "name": "RR"
            },
            {
             "t": "check",
             "name": "ciRR",
             "children": [
              {
               "t": "text",
               "name": "ciWidthRR",
               "label": "Interval",
               "format": "number",
               "enable": "ciRR"
              }
             ],
             "enable": "RR"
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Estimated Marginal Means",
     "collapsed": true,
     "children": [
      {
       "t": "supplier",
       "targets": []
      },
      {
       "t": "grid",
       "cells": [
        {
         "col": 0,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "General Options",
           "children": [
            {
             "t": "check",
             "name": "emmWeights"
            },
            {
             "t": "check",
             "name": "ciEmm",
             "children": [
              {
               "t": "text",
               "name": "ciWidthEmm",
               "label": "Interval",
               "format": "number",
               "enable": "ciEmm"
              }
             ]
            }
           ]
          }
         ]
        },
        {
         "col": 1,
         "row": 0,
         "children": [
          {
           "t": "label",
           "label": "Output",
           "children": [
            {
             "t": "check",
             "name": "emmPlots"
            },
            {
             "t": "check",
             "name": "emmTables"
            }
           ]
          }
         ]
        }
       ]
      }
     ]
    }
   ]
  }
 },
 "reliability": {
  "name": "reliability",
  "ns": "jmv",
  "title": "Reliability Analysis",
  "menuGroup": "Factor",
  "menuSubgroup": "Scale Analysis",
  "menuTitle": "Reliability Analysis",
  "menuSubtitle": "",
  "options": [
   {
    "name": "vars",
    "type": "Variables",
    "title": "Items",
    "default": null,
    "suggested": [
     "ordinal",
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "alphaScale",
    "type": "Bool",
    "title": "Cronbach's α",
    "default": true
   },
   {
    "name": "omegaScale",
    "type": "Bool",
    "title": "McDonald's ω",
    "default": false
   },
   {
    "name": "meanScale",
    "type": "Bool",
    "title": "Mean",
    "default": false
   },
   {
    "name": "sdScale",
    "type": "Bool",
    "title": "Standard deviation",
    "default": false
   },
   {
    "name": "corPlot",
    "type": "Bool",
    "title": "Correlation Heatmap",
    "default": false
   },
   {
    "name": "alphaItems",
    "type": "Bool",
    "title": "Cronbach's α (if item is dropped)",
    "default": false
   },
   {
    "name": "omegaItems",
    "type": "Bool",
    "title": "McDonald's ω (if item is dropped)",
    "default": false
   },
   {
    "name": "meanItems",
    "type": "Bool",
    "title": "Mean",
    "default": false
   },
   {
    "name": "sdItems",
    "type": "Bool",
    "title": "Standard deviation",
    "default": false
   },
   {
    "name": "itemRestCor",
    "type": "Bool",
    "title": "Item-rest correlation",
    "default": false
   },
   {
    "name": "revItems",
    "type": "Variables",
    "title": "Reverse Scaled Items",
    "default": null,
    "suggested": [],
    "permitted": []
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "vars"
      }
     ]
    },
    {
     "t": "grid",
     "cells": [
      {
       "col": 0,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Scale Statistics",
         "children": [
          {
           "t": "check",
           "name": "alphaScale"
          },
          {
           "t": "check",
           "name": "omegaScale"
          },
          {
           "t": "check",
           "name": "meanScale"
          },
          {
           "t": "check",
           "name": "sdScale"
          }
         ]
        },
        {
         "t": "label",
         "label": "Additional Options",
         "children": [
          {
           "t": "check",
           "name": "corPlot",
           "label": "Correlation heatmap"
          }
         ]
        }
       ]
      },
      {
       "col": 1,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Item Statistics",
         "children": [
          {
           "t": "check",
           "name": "alphaItems"
          },
          {
           "t": "check",
           "name": "omegaItems"
          },
          {
           "t": "check",
           "name": "meanItems"
          },
          {
           "t": "check",
           "name": "sdItems"
          },
          {
           "t": "check",
           "name": "itemRestCor"
          }
         ]
        }
       ]
      }
     ]
    }
   ]
  }
 },
 "pca": {
  "name": "pca",
  "ns": "jmv",
  "title": "Principal Component Analysis",
  "menuGroup": "Factor",
  "menuSubgroup": "Data Reduction",
  "menuTitle": "Principal Component Analysis",
  "menuSubtitle": "",
  "options": [
   {
    "name": "vars",
    "type": "Variables",
    "title": "Variables",
    "default": null,
    "suggested": [
     "ordinal",
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "nFactorMethod",
    "type": "List",
    "title": "Number of components",
    "default": "parallel",
    "choices": [
     {
      "value": "parallel",
      "title": "parallel"
     },
     {
      "value": "eigen",
      "title": "eigen"
     },
     {
      "value": "fixed",
      "title": "fixed"
     }
    ]
   },
   {
    "name": "nFactors",
    "type": "Integer",
    "title": "nFactors",
    "default": 1,
    "min": 1
   },
   {
    "name": "minEigen",
    "type": "Number",
    "title": "Minimum value",
    "default": 1
   },
   {
    "name": "rotation",
    "type": "List",
    "title": "Rotation",
    "default": "varimax",
    "choices": [
     {
      "value": "none",
      "title": "None"
     },
     {
      "value": "varimax",
      "title": "Varimax"
     },
     {
      "value": "quartimax",
      "title": "Quartimax"
     },
     {
      "value": "promax",
      "title": "Promax"
     },
     {
      "value": "oblimin",
      "title": "Oblimin"
     },
     {
      "value": "simplimax",
      "title": "Simplimax"
     }
    ]
   },
   {
    "name": "hideLoadings",
    "type": "Number",
    "title": "Hide loadings below",
    "default": 0.3
   },
   {
    "name": "sortLoadings",
    "type": "Bool",
    "title": "Sort loadings by size",
    "default": false
   },
   {
    "name": "screePlot",
    "type": "Bool",
    "title": "Scree plot",
    "default": false
   },
   {
    "name": "eigen",
    "type": "Bool",
    "title": "Initial eigenvalues",
    "default": false
   },
   {
    "name": "factorCor",
    "type": "Bool",
    "title": "Component correlations",
    "default": false
   },
   {
    "name": "factorSummary",
    "type": "Bool",
    "title": "Component summary",
    "default": false
   },
   {
    "name": "kmo",
    "type": "Bool",
    "title": "KMO measure of sampling adequacy",
    "default": false
   },
   {
    "name": "bartlett",
    "type": "Bool",
    "title": "Bartlett's test of sphericity",
    "default": false
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "vars"
      }
     ]
    },
    {
     "t": "grid",
     "cells": [
      {
       "col": 0,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Method",
         "children": [
          {
           "t": "combo",
           "name": "rotation",
           "label": ""
          }
         ]
        },
        {
         "t": "label",
         "label": "Number of Components",
         "children": [
          {
           "t": "radio",
           "option": "nFactorMethod",
           "part": "parallel",
           "label": "Based on parallel analysis"
          },
          {
           "t": "radio",
           "option": "nFactorMethod",
           "part": "eigen",
           "label": "Based on eigenvalue"
          },
          {
           "t": "radio",
           "option": "nFactorMethod",
           "part": "fixed",
           "label": "Fixed number"
          }
         ]
        }
       ]
      },
      {
       "col": 1,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Assumption Checks",
         "children": [
          {
           "t": "check",
           "name": "bartlett"
          },
          {
           "t": "check",
           "name": "kmo"
          }
         ]
        },
        {
         "t": "label",
         "label": "Factor Loadings",
         "children": [
          {
           "t": "text",
           "name": "hideLoadings",
           "label": "",
           "format": "number"
          },
          {
           "t": "check",
           "name": "sortLoadings"
          }
         ]
        },
        {
         "t": "label",
         "label": "Additional Output",
         "children": [
          {
           "t": "check",
           "name": "factorSummary"
          },
          {
           "t": "check",
           "name": "factorCor"
          },
          {
           "t": "check",
           "name": "eigen"
          },
          {
           "t": "check",
           "name": "screePlot"
          }
         ]
        }
       ]
      }
     ]
    }
   ]
  }
 },
 "efa": {
  "name": "efa",
  "ns": "jmv",
  "title": "Exploratory Factor Analysis",
  "menuGroup": "Factor",
  "menuSubgroup": "Data Reduction",
  "menuTitle": "Exploratory Factor Analysis",
  "menuSubtitle": "",
  "options": [
   {
    "name": "vars",
    "type": "Variables",
    "title": "Variables",
    "default": null,
    "suggested": [
     "ordinal",
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "nFactorMethod",
    "type": "List",
    "title": "Number of factors",
    "default": "parallel",
    "choices": [
     {
      "value": "parallel",
      "title": "Based on parallel analysis"
     },
     {
      "value": "eigen",
      "title": "Based on eigenvalue"
     },
     {
      "value": "fixed",
      "title": "Fixed number"
     }
    ]
   },
   {
    "name": "nFactors",
    "type": "Integer",
    "title": "nFactors",
    "default": 1,
    "min": 1
   },
   {
    "name": "minEigen",
    "type": "Number",
    "title": "Minimum value",
    "default": 0
   },
   {
    "name": "extraction",
    "type": "List",
    "title": "Extraction",
    "default": "minres",
    "choices": [
     {
      "value": "minres",
      "title": "Minimum residuals"
     },
     {
      "value": "ml",
      "title": "Maximum likelihood"
     },
     {
      "value": "pa",
      "title": "Principal axis"
     }
    ]
   },
   {
    "name": "rotation",
    "type": "List",
    "title": "Rotation",
    "default": "oblimin",
    "choices": [
     {
      "value": "none",
      "title": "None"
     },
     {
      "value": "varimax",
      "title": "Varimax"
     },
     {
      "value": "quartimax",
      "title": "Quartimax"
     },
     {
      "value": "promax",
      "title": "Promax"
     },
     {
      "value": "oblimin",
      "title": "Oblimin"
     },
     {
      "value": "simplimax",
      "title": "Simplimax"
     }
    ]
   },
   {
    "name": "hideLoadings",
    "type": "Number",
    "title": "Hide loadings below",
    "default": 0.3
   },
   {
    "name": "sortLoadings",
    "type": "Bool",
    "title": "Sort loadings by size",
    "default": false
   },
   {
    "name": "screePlot",
    "type": "Bool",
    "title": "Scree plot",
    "default": false
   },
   {
    "name": "eigen",
    "type": "Bool",
    "title": "Initial eigenvalues",
    "default": false
   },
   {
    "name": "factorCor",
    "type": "Bool",
    "title": "Factor correlations",
    "default": false
   },
   {
    "name": "factorSummary",
    "type": "Bool",
    "title": "Factor summary",
    "default": false
   },
   {
    "name": "modelFit",
    "type": "Bool",
    "title": "Model fit measures",
    "default": false
   },
   {
    "name": "kmo",
    "type": "Bool",
    "title": "KMO measure of sampling adequacy",
    "default": false
   },
   {
    "name": "bartlett",
    "type": "Bool",
    "title": "Bartlett's test of sphericity",
    "default": false
   },
   {
    "name": "factorScoreMethod",
    "type": "List",
    "title": "Estimation method",
    "default": "Thurstone",
    "choices": [
     {
      "value": "Thurstone",
      "title": "Thurstone"
     },
     {
      "value": "Bartlett",
      "title": "Bartlett"
     },
     {
      "value": "tenBerge",
      "title": "ten Berge"
     },
     {
      "value": "Anderson",
      "title": "Anderson & Rubin"
     },
     {
      "value": "Harman",
      "title": "Harman"
     }
    ]
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "vars"
      }
     ]
    },
    {
     "t": "grid",
     "cells": [
      {
       "col": 0,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Method",
         "children": [
          {
           "t": "combo",
           "name": "extraction",
           "label": ""
          },
          {
           "t": "combo",
           "name": "rotation",
           "label": ""
          }
         ]
        },
        {
         "t": "label",
         "label": "Number of Factors",
         "children": [
          {
           "t": "radio",
           "option": "nFactorMethod",
           "part": "parallel",
           "label": "parallel"
          },
          {
           "t": "radio",
           "option": "nFactorMethod",
           "part": "eigen",
           "label": "eigen"
          },
          {
           "t": "radio",
           "option": "nFactorMethod",
           "part": "fixed",
           "label": "fixed"
          }
         ]
        }
       ]
      },
      {
       "col": 1,
       "row": 0,
       "children": [
        {
         "t": "label",
         "label": "Assumption Checks",
         "children": [
          {
           "t": "check",
           "name": "bartlett"
          },
          {
           "t": "check",
           "name": "kmo"
          }
         ]
        },
        {
         "t": "label",
         "label": "Factor Loadings",
         "children": [
          {
           "t": "text",
           "name": "hideLoadings",
           "label": "",
           "format": "number"
          },
          {
           "t": "check",
           "name": "sortLoadings"
          }
         ]
        },
        {
         "t": "label",
         "label": "Additional Output",
         "children": [
          {
           "t": "check",
           "name": "factorSummary"
          },
          {
           "t": "check",
           "name": "factorCor"
          },
          {
           "t": "check",
           "name": "modelFit"
          },
          {
           "t": "check",
           "name": "eigen"
          },
          {
           "t": "check",
           "name": "screePlot"
          }
         ]
        }
       ]
      }
     ]
    },
    {
     "t": "collapse",
     "label": "Save",
     "collapsed": true,
     "children": [
      {
       "t": "combo",
       "name": "factorScoreMethod",
       "label": ""
      }
     ]
    }
   ]
  }
 },
 "scat": {
  "name": "scat",
  "ns": "scatr",
  "title": "Scatter Plot",
  "menuGroup": "Exploration",
  "menuSubgroup": "scatr",
  "menuTitle": "Scatter Plot",
  "menuSubtitle": "",
  "options": [
   {
    "name": "x",
    "type": "Variable",
    "title": "X-Axis",
    "default": null,
    "suggested": [
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "y",
    "type": "Variable",
    "title": "Y-Axis",
    "default": null,
    "suggested": [
     "continuous"
    ],
    "permitted": [
     "numeric"
    ]
   },
   {
    "name": "group",
    "type": "Variable",
    "title": "Grouping Variable",
    "default": null,
    "suggested": [
     "nominal"
    ],
    "permitted": [
     "factor"
    ]
   },
   {
    "name": "flipAxes",
    "type": "Bool",
    "title": "Flip axes",
    "default": false
   },
   {
    "name": "pointSize",
    "type": "Number",
    "title": "Point size",
    "default": 2
   },
   {
    "name": "regLine",
    "type": "Bool",
    "title": "Show line",
    "default": false
   },
   {
    "name": "lineMethod",
    "type": "List",
    "title": "Method",
    "default": "lm",
    "choices": [
     {
      "value": "lm",
      "title": "Linear"
     },
     {
      "value": "loess",
      "title": "Smooth"
     }
    ]
   },
   {
    "name": "lineSE",
    "type": "Bool",
    "title": "Confidence interval",
    "default": true
   },
   {
    "name": "title",
    "type": "String",
    "title": "Title text",
    "default": ""
   },
   {
    "name": "titleAlign",
    "type": "List",
    "title": "Align",
    "default": "center",
    "choices": [
     {
      "value": "left",
      "title": "Left"
     },
     {
      "value": "center",
      "title": "Center"
     },
     {
      "value": "right",
      "title": "Right"
     }
    ]
   },
   {
    "name": "titleFontSize",
    "type": "Number",
    "title": "Font size",
    "default": 16
   },
   {
    "name": "titleFontFace",
    "type": "List",
    "title": "Font face",
    "default": "plain",
    "choices": [
     {
      "value": "plain",
      "title": "Plain"
     },
     {
      "value": "bold",
      "title": "Bold"
     },
     {
      "value": "italic",
      "title": "Italic"
     },
     {
      "value": "bold-italic",
      "title": "Bold Italic"
     }
    ]
   },
   {
    "name": "subtitle",
    "type": "String",
    "title": "Title text",
    "default": ""
   },
   {
    "name": "subtitleAlign",
    "type": "List",
    "title": "Align",
    "default": "left",
    "choices": [
     {
      "value": "left",
      "title": "Left"
     },
     {
      "value": "center",
      "title": "Center"
     },
     {
      "value": "right",
      "title": "Right"
     }
    ]
   },
   {
    "name": "subtitleFontSize",
    "type": "Number",
    "title": "Font size",
    "default": 16
   },
   {
    "name": "subtitleFontFace",
    "type": "List",
    "title": "Font face",
    "default": "plain",
    "choices": [
     {
      "value": "plain",
      "title": "Plain"
     },
     {
      "value": "bold",
      "title": "Bold"
     },
     {
      "value": "italic",
      "title": "Italic"
     },
     {
      "value": "bold-italic",
      "title": "Bold Italic"
     }
    ]
   },
   {
    "name": "caption",
    "type": "String",
    "title": "Title text",
    "default": ""
   },
   {
    "name": "captionAlign",
    "type": "List",
    "title": "Align",
    "default": "right",
    "choices": [
     {
      "value": "left",
      "title": "Left"
     },
     {
      "value": "center",
      "title": "Center"
     },
     {
      "value": "right",
      "title": "Right"
     }
    ]
   },
   {
    "name": "captionFontSize",
    "type": "Number",
    "title": "Font size",
    "default": 12
   },
   {
    "name": "captionFontFace",
    "type": "List",
    "title": "Font face",
    "default": "plain",
    "choices": [
     {
      "value": "plain",
      "title": "Plain"
     },
     {
      "value": "bold",
      "title": "Bold"
     },
     {
      "value": "italic",
      "title": "Italic"
     },
     {
      "value": "bold-italic",
      "title": "Bold Italic"
     }
    ]
   },
   {
    "name": "xLabel",
    "type": "String",
    "title": "Title text",
    "default": ""
   },
   {
    "name": "xLabelAlign",
    "type": "List",
    "title": "Align",
    "default": "center",
    "choices": [
     {
      "value": "left",
      "title": "Left"
     },
     {
      "value": "center",
      "title": "Center"
     },
     {
      "value": "right",
      "title": "Right"
     }
    ]
   },
   {
    "name": "xLabelFontSize",
    "type": "Number",
    "title": "Font size",
    "default": 16
   },
   {
    "name": "xLabelFontFace",
    "type": "List",
    "title": "Font face",
    "default": "plain",
    "choices": [
     {
      "value": "plain",
      "title": "Plain"
     },
     {
      "value": "bold",
      "title": "Bold"
     },
     {
      "value": "italic",
      "title": "Italic"
     },
     {
      "value": "bold-italic",
      "title": "Bold Italic"
     }
    ]
   },
   {
    "name": "yLabel",
    "type": "String",
    "title": "Title text",
    "default": ""
   },
   {
    "name": "yLabelAlign",
    "type": "List",
    "title": "Align",
    "default": "center",
    "choices": [
     {
      "value": "left",
      "title": "Left"
     },
     {
      "value": "center",
      "title": "Center"
     },
     {
      "value": "right",
      "title": "Right"
     }
    ]
   },
   {
    "name": "yLabelFontSize",
    "type": "Number",
    "title": "Font size",
    "default": 16
   },
   {
    "name": "yLabelFontFace",
    "type": "List",
    "title": "Font face",
    "default": "plain",
    "choices": [
     {
      "value": "plain",
      "title": "Plain"
     },
     {
      "value": "bold",
      "title": "Bold"
     },
     {
      "value": "italic",
      "title": "Italic"
     },
     {
      "value": "bold-italic",
      "title": "Bold Italic"
     }
    ]
   },
   {
    "name": "titleType",
    "type": "List",
    "title": "titleType",
    "default": "title",
    "choices": [
     {
      "value": "title",
      "title": "Plot Title"
     },
     {
      "value": "subtitle",
      "title": "Plot Subtitle"
     },
     {
      "value": "caption",
      "title": "Plot Caption"
     },
     {
      "value": "xTitle",
      "title": "X-Axis Title"
     },
     {
      "value": "yTitle",
      "title": "Y-Axis Title"
     }
    ]
   },
   {
    "name": "yAxisLabelFontSize",
    "type": "Number",
    "title": "Label font size",
    "default": 12
   },
   {
    "name": "yAxisLabelRotation",
    "type": "Number",
    "title": "Label rotation",
    "default": 0,
    "min": 0,
    "max": 360
   },
   {
    "name": "yAxisRangeType",
    "type": "List",
    "title": "Y-Axis Range",
    "default": "auto",
    "choices": [
     {
      "value": "auto",
      "title": "Auto"
     },
     {
      "value": "manual",
      "title": "Manual"
     }
    ]
   },
   {
    "name": "yAxisRangeMin",
    "type": "Number",
    "title": "Min",
    "default": 0
   },
   {
    "name": "yAxisRangeMax",
    "type": "Number",
    "title": "Max",
    "default": 10
   },
   {
    "name": "xAxisLabelFontSize",
    "type": "Number",
    "title": "Label font size",
    "default": 12
   },
   {
    "name": "xAxisLabelRotation",
    "type": "Number",
    "title": "Label rotation",
    "default": 0,
    "min": 0,
    "max": 360
   },
   {
    "name": "xAxisRangeType",
    "type": "List",
    "title": "X-Axis Range",
    "default": "auto",
    "choices": [
     {
      "value": "auto",
      "title": "Auto"
     },
     {
      "value": "manual",
      "title": "Manual"
     }
    ]
   },
   {
    "name": "xAxisRangeMin",
    "type": "Number",
    "title": "Min",
    "default": 0
   },
   {
    "name": "xAxisRangeMax",
    "type": "Number",
    "title": "Max",
    "default": 10
   },
   {
    "name": "legendTitle",
    "type": "String",
    "title": "Title text",
    "default": ""
   },
   {
    "name": "legendTitleFontSize",
    "type": "Number",
    "title": "Title font size",
    "default": 16
   },
   {
    "name": "legendTitleFontFace",
    "type": "List",
    "title": "Title font face",
    "default": "plain",
    "choices": [
     {
      "value": "plain",
      "title": "Plain"
     },
     {
      "value": "bold",
      "title": "Bold"
     },
     {
      "value": "italic",
      "title": "Italic"
     },
     {
      "value": "bold-italic",
      "title": "Bold Italic"
     }
    ]
   },
   {
    "name": "legendLabelFontSize",
    "type": "Number",
    "title": "Label font size",
    "default": 16
   },
   {
    "name": "legendLabelFontFace",
    "type": "List",
    "title": "Label font face",
    "default": "plain",
    "choices": [
     {
      "value": "plain",
      "title": "Plain"
     },
     {
      "value": "bold",
      "title": "Bold"
     },
     {
      "value": "italic",
      "title": "Italic"
     },
     {
      "value": "bold-italic",
      "title": "Bold Italic"
     }
    ]
   },
   {
    "name": "legendKeyWidth",
    "type": "Number",
    "title": "Key width",
    "default": 0.6,
    "min": 0
   },
   {
    "name": "legendKeyHeight",
    "type": "Number",
    "title": "Key height",
    "default": 0.6,
    "min": 0
   },
   {
    "name": "legenPositionType",
    "type": "List",
    "title": "legenPositionType",
    "default": "outside",
    "choices": [
     {
      "value": "outside",
      "title": "Outside"
     },
     {
      "value": "inside",
      "title": "Inside"
     },
     {
      "value": "hide",
      "title": "Hide"
     }
    ]
   },
   {
    "name": "legendPosition",
    "type": "List",
    "title": "Position",
    "default": "right",
    "choices": [
     {
      "value": "top",
      "title": "Top"
     },
     {
      "value": "right",
      "title": "Right"
     },
     {
      "value": "bottom",
      "title": "Bottom"
     },
     {
      "value": "left",
      "title": "Left"
     }
    ]
   },
   {
    "name": "legendJustification",
    "type": "List",
    "title": "Justification",
    "default": "center",
    "choices": [
     {
      "value": "center",
      "title": "Center"
     },
     {
      "value": "top",
      "title": "Top"
     },
     {
      "value": "right",
      "title": "Right"
     },
     {
      "value": "bottom",
      "title": "Bottom"
     },
     {
      "value": "left",
      "title": "Left"
     }
    ]
   },
   {
    "name": "legendPositionX",
    "type": "Number",
    "title": "X-position",
    "default": 0.8,
    "min": 0,
    "max": 1
   },
   {
    "name": "legendPositionY",
    "type": "Number",
    "title": "Y-position",
    "default": 0.5,
    "min": 0,
    "max": 1
   },
   {
    "name": "legendDirection",
    "type": "List",
    "title": "Direction",
    "default": "vertical",
    "choices": [
     {
      "value": "horizontal",
      "title": "Horizontal"
     },
     {
      "value": "vertical",
      "title": "Vertical"
     }
    ]
   }
  ],
  "layout": {
   "t": "root",
   "children": [
    {
     "t": "supplier",
     "targets": [
      {
       "name": "x",
       "max": 1
      },
      {
       "name": "y",
       "max": 1
      },
      {
       "name": "group",
       "max": 1
      }
     ]
    },
    {
     "t": "grid",
     "cells": [
      {
       "col": 0,
       "row": 0,
       "children": []
      },
      {
       "col": 1,
       "row": 0,
       "children": []
      }
     ]
    }
   ]
  }
 }
};
