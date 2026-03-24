# Bloomberg Terminal interface
# Replace this file with your own implementation.
# app.py expects:
#   bdh(securities, fields, start_date, end_date) -> pd.DataFrame
#     columns: security | date | <fields...>
#   bdp(securities, fields) -> pd.DataFrame
#     columns: security | <fields...>


def bdh(securities, fields, start_date, end_date):
    raise NotImplementedError("Replace bbg.py with your Bloomberg implementation.")


def bdp(securities, fields):
    raise NotImplementedError("Replace bbg.py with your Bloomberg implementation.")
