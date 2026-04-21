"""
py2m — Python/pandas to microdata.no script translator.

Quick start:
    from py2m import transform

    result = transform(python_source_code, df_name='df')
    print(result.script())
    for w in result.warnings:
        print("WARNING:", w)
"""
from .transformer import Py2MTransformer, TranslationResult


def transform(source: str, df_name: str = "df", dataset_name: str = None) -> TranslationResult:
    """
    Translate Python/pandas source code to a microdata.no script.

    Parameters
    ----------
    source       : str  — Python source code to translate
    df_name      : str  — name of the main DataFrame variable (default 'df')
    dataset_name : str  — microdata name of the active dataset (used to emit
                          'use <dataset_name>' after to_microdata() collapses)

    Returns
    -------
    TranslationResult with .script() → str and .warnings → list[str]
    """
    return Py2MTransformer(df_name=df_name, dataset_name=dataset_name).transform(source)


__all__ = ["transform", "Py2MTransformer", "TranslationResult"]
