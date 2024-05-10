import re
import string
from io import BytesIO

import numexpr as ne
import pandas as pd
import streamlit as st
from scipy.stats import t
import numpy as np


def convert_to_cell_reference(lookup_value, df, table_array_cols):
    for col in table_array_cols:
        matching_rows = df[df[col] == lookup_value]
        if not matching_rows.empty:
            if len(matching_rows) == 1:
                lookup_row = matching_rows.index[0]
                lookup_col = df.columns.get_loc(col)
                return get_cell_reference(lookup_row, lookup_col)
            else:
                st.write(f"Multiple occurrences found for value '{lookup_value}' in column '{col}':")
                options = []
                for idx, row in matching_rows.iterrows():
                    options.append(f"Row {idx + 1}: {', '.join(str(val) for val in row.values)}")
                selected_option = st.radio("Select the row to use:", options)
                selected_row = int(selected_option.split(":")[0].split(" ")[1]) - 1
                lookup_row = matching_rows.index[selected_row]
                lookup_col = df.columns.get_loc(col)
                return get_cell_reference(lookup_row, lookup_col)
    st.warning(f"No matching value found for '{lookup_value}'. Please enter a valid lookup value.")
    return None
def extract_numbers_with_variable_names(question):
    matches = re.findall(r'\d+(?:,\d{3})*(?:\.\d+)?', question)
    numbers = [float(match.replace(',', '')) for match in matches]
    variable_names = list(string.ascii_uppercase)[:len(numbers)]
    return numbers, variable_names


# def evaluate_formula(formula, variables_dict):
#     try:
#         return ne.evaluate(formula, local_dict=variables_dict)
#     except Exception as e:
#         return str(e)


def convert_to_dataframe(raw_data):
    try:
        if 'df' not in st.session_state:
            st.session_state['df'] = None
        df = pd.read_csv(pd.io.common.StringIO(raw_data), sep='\t', engine='python')
        for col in df.columns:
            if df[col].dtype == object:
                try:
                    df[col] = df[col].replace('[\$,]', '', regex=True).replace(',', '', regex=True).astype(float)
                    st.session_state['df'] = df
                except ValueError:
                    pass
        return df, list(df.columns)
    except Exception as e:
        st.error(f"Error parsing CSV data: {e}")
        return None, None


def sanitize_formula(formula):
    cleaned_formula = re.sub(r'[\r\n\t]+', '', formula)
    cleaned_formula = re.sub(r'(\d+\.\d+)([A-Za-z]+)', r'\1*\2', cleaned_formula)
    return cleaned_formula


def parse_and_compute(formula, computed_values):
    sanitized_formula = sanitize_formula(formula)
    # Continue with the replacement of variables with their numeric values
    for var, value in computed_values.items():
        if var in sanitized_formula:
            sanitized_formula = sanitized_formula.replace(var, str(value))

    sanitized_formula = sanitized_formula.replace('%', '/100')

    try:
        result = ne.evaluate(sanitized_formula)
    except Exception as e:
        print(f"Error evaluating formula: {e}")
        result = None

    if result is not None:
        try:
            result = float(result)
        except ValueError:
            print("Conversion to float failed, setting result to None")
            result = None

    return result

    variables_in_formula = re.findall(r'[A-Za-z]+', formula)

    # Replace each variable in the formula with its value from computed_values
    for var in variables_in_formula:
        if var in computed_values:
            # Replace the variable name with its value, ensure it's cast to str for replacement
            formula = formula.replace(var, str(computed_values[var]))

    # Evaluate the formula using numexpr for safety
    try:
        # Use ne.evaluate to compute the result of the formula
        return ne.evaluate(formula)
    except Exception as e:
        # If there's an error in evaluation, return the error message
        return str(e)


def apply_solution(params, formulas, variable_values):
    # Initialize a dictionary to store computed results
    computed_values = variable_values.copy()
    results = []

    # Iterate over each solution parameter and its formula
    for param, formula in zip(params, formulas):
        if formula.startswith("margin_of_error"):
            # If the formula starts with "margin_of_error", extract the variable names
            alpha_var, std_var, size_var = re.findall(r'\((.*?)\)', formula)[0].split(', ')

            # Get the values for the variables from variable_values or use default values
            alpha = float(variable_values.get(alpha_var, 0.05))
            std = float(variable_values.get(std_var, 0))
            size = int(variable_values.get(size_var, 0))

            if std != 0 and size != 0:
                df = size - 1
                t_critical = t.ppf(1 - alpha / 2, df)
                result = t_critical * (std / np.sqrt(size))
            else:
                result = None
        else:
            # Compute the result of the formula
            result = parse_and_compute(formula, computed_values)

        # Update the computed values with the result
        computed_values[param] = result
        # Append the result to the results list
        results.append((param, result))

    # Return the results as a list of tuples
    return results


def handle_table_input():
    if 'show_table_input' not in st.session_state:
        st.session_state['show_table_input'] = False

    if 'raw_data' not in st.session_state:
        st.session_state['raw_data'] = ''

    if 'df' not in st.session_state:
        st.session_state['df'] = None

    show_table_input_button = st.button("Add table",key="show_table_input_button")

    if show_table_input_button:
        st.session_state['show_table_input'] = True

    if st.session_state['show_table_input']:
        st.session_state['raw_data'] = st.text_area("Table data", st.session_state['raw_data'])
        convert_button = st.button("Convert")
        if st.session_state['raw_data'] is None:
            st.error("No table has been added")

        if convert_button:
            df, columns = convert_to_dataframe(st.session_state['raw_data'])
            if df is not None:
                st.session_state['df'] = df
                st.session_state['show_table_input'] = False
            else:
                st.error("Error converting data to DataFrame.")

    if st.session_state['df'] is not None:
        st.write("Full Table:")
        st.dataframe(st.session_state['df'])

def excel_to_dataframe_reference(cell):
    match = re.match(r"([A-Z]+)([0-9]+)", cell)
    if match:
        col, row = match.groups()
        row = int(row) - 1  # Convert to zero-based index
        col = ord(col) - 65  # Convert 'A' to 0, 'B' to 1, etc.
        return row, col
    else:
        raise ValueError(f"Invalid cell reference '{cell}'. Cell reference must contain a column and a row number.")


def evaluate_formula(formula, sheet):
    if formula.startswith("="):
        formula = formula[1:]  # Remove the leading '='

    # Replace cell references with their corresponding values
    cell_refs = re.findall(r"[A-Z]+[0-9]+", formula)
    for cell_ref in cell_refs:
        row, col = excel_to_dataframe_reference(cell_ref)
        cell_value = sheet.cell(row=row + 1, column=col + 1).value
        if isinstance(cell_value, str) and cell_value.startswith("="):
            cell_value = evaluate_formula(cell_value, sheet)
        formula = formula.replace(cell_ref, str(cell_value))

    # Evaluate the formula
    try:
        result = eval(formula)
        return result
    except Exception as e:
        raise ValueError(f"Error evaluating formula: {formula}. {str(e)}")


def get_cell_reference(row, col):
    col_name = chr(65 + col)
    return f"{col_name}{row + 1}"

table_array_cols=[]
def apply_formula(formula_choice, input_values, target_cell, previous_output=None):
    df = st.session_state['df']
    if previous_output is not None:
        input_values['previous_output'] = previous_output
    if formula_choice == "SUM":
        start_cell, end_cell = input_values['range'].split(':')
        start_row, start_col = excel_to_dataframe_reference(start_cell)
        end_row, end_col = excel_to_dataframe_reference(end_cell)
        formula = f"=SUM({get_cell_reference(start_row, start_col)}:{get_cell_reference(end_row, end_col)})"
    elif formula_choice == "SUMIF":
        range_ = input_values['range']
        criteria_range = input_values['criteria_range']
        criteria = input_values['criteria']
        formula = f"=SUMIF({criteria_range}, {criteria}, {range_})"
    elif formula_choice == "VLOOKUP":
        lookup_value = input_values["lookup_value"]
        if isinstance(lookup_value, tuple):
            child_formula, child_target_cell = lookup_value
            lookup_value = apply_formula(child_formula, input_values[child_formula], child_target_cell)

        if table_array_cols:
            table_array_range = f"{get_cell_reference(1, df.columns.get_loc(table_array_cols[0]))}:{get_cell_reference(len(df), df.columns.get_loc(table_array_cols[-1]))}"
        else:
            table_array_range = ""
        lookup_value = convert_to_cell_reference(lookup_value, df, table_array_cols)

        col_index_num = input_values["col_index_num"]
        if lookup_value:
            formula = f'=VLOOKUP({lookup_value}, {table_array_range}, {col_index_num}, {input_values["range_lookup"]})'
        else:
            formula = ""
    elif formula_choice == "MATCH":
        lookup_value = input_values["lookup_value"]
        if isinstance(lookup_value, tuple):
            child_formula, child_target_cell = lookup_value
            lookup_value = apply_formula(child_formula, input_values[child_formula], child_target_cell)

        lookup_array_cols = input_values["lookup_array"]
        if lookup_array_cols:
            lookup_array_start = get_cell_reference(0, df.columns.get_loc(lookup_array_cols[0]))
            lookup_array_end = get_cell_reference(len(df) - 1, df.columns.get_loc(lookup_array_cols[-1]))
            lookup_array = f"{lookup_array_start}:{lookup_array_end}"
        else:
            st.warning("Please select at least one column for the lookup array.")
            lookup_array = ""

        match_type = input_values["match_type"]
        formula = f'=MATCH({lookup_value}, {lookup_array}, {match_type})'

    elif formula_choice == "INDEX":
        array_start, array_end = input_values["array"].split(':')
        array_start_row, array_start_col = excel_to_dataframe_reference(array_start)
        array_end_row, array_end_col = excel_to_dataframe_reference(array_end)
        array = f"{get_cell_reference(array_start_row, array_start_col)}:{get_cell_reference(array_end_row, array_end_col)}"

        row_num = input_values["row_num"]
        if isinstance(row_num, tuple):
            child_formula, child_target_cell = row_num
            row_num = apply_formula(child_formula, input_values[child_formula], child_target_cell)
        else:
            row_num_row, row_num_col = excel_to_dataframe_reference(row_num)
            row_num = get_cell_reference(row_num_row, row_num_col)

        col_num = input_values.get("col_num", "")
        if col_num:
            if isinstance(col_num, tuple):
                child_formula, child_target_cell = col_num
                col_num = apply_formula(child_formula, input_values[child_formula], child_target_cell)
            else:
                col_num_row, col_num_col = excel_to_dataframe_reference(col_num)
                col_num = get_cell_reference(col_num_row, col_num_col)
            formula = f'=INDEX({array}, {row_num}, {col_num})'
        else:
            formula = f'=INDEX({array}, {row_num})'
    elif formula_choice == "AVG":
        start_cell, end_cell = input_values['range'].split(':')
        start_row, start_col = excel_to_dataframe_reference(start_cell)
        end_row, end_col = excel_to_dataframe_reference(end_cell)
        formula = f"=AVERAGE({get_cell_reference(start_row, start_col)}:{get_cell_reference(end_row, end_col)})"
    else:
        raise ValueError(f"Unknown formula: {formula_choice}")

    # Apply the formula to the Excel file
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
        workbook = writer.book
        sheet = workbook.active
        sheet[target_cell] = f'={formula}'
        writer.save()
    output.seek(0)
    df_with_formula = pd.read_excel(output)

    target_row, target_col = excel_to_dataframe_reference(target_cell)

    formula_output = df_with_formula.iat[target_row, target_col]
    st.write(f"Formula `{formula}` applied at cell {target_cell}. Output: {formula_output}")
    output.seek(0)
    st.download_button(
        label="Download Excel file",
        data=output,
        file_name="modified_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return formula_output


def formula_inputs():
    formula_choice = st.selectbox("Select a formula", ["SUM", "SUMIF", "VLOOKUP", "MATCH", "INDEX", "AVG"])
    input_values = {}
    df = st.session_state['df']
    table_array_cols = []
    if formula_choice in ["SUM", "AVG"]:
        range_ = st.text_input("Enter the range (e.g., 'A1:B5'):")
        input_values['range'] = range_
    elif formula_choice == "SUMIF":
        criteria_range = st.text_input("Enter the criteria range (e.g., 'A1:A5'):")
        input_values['criteria_range'] = criteria_range
        criteria = st.text_input("Enter the criteria (e.g., 'apple'):")
        input_values['criteria'] = criteria

        # Let the user select the columns for the range
        range_cols = st.multiselect("Select the columns for the range:", options=df.columns.tolist())

        # Construct the range string
        if range_cols:
            range_start = get_cell_reference(1, df.columns.get_loc(range_cols[0]))  # Start from the 2nd row
            range_end = get_cell_reference(len(df) - 1, df.columns.get_loc(range_cols[-1]))  # End at the last row
            range_ = f"{range_start}:{range_end}"
        else:
            st.warning("Please select at least one column for the range.")
            range_ = ""

        input_values['range'] = range_
    elif formula_choice == "VLOOKUP":
        lookup_value_type = st.selectbox("Select lookup value type:", options=["Value", "Formula"])
        if lookup_value_type == "Value":
            lookup_value = st.text_input("Enter the lookup value:")
            input_values['lookup_value'] = lookup_value

            if table_array_cols:
                matching_rows = df[df[table_array_cols[0]] == lookup_value]
                if not matching_rows.empty:
                    if len(matching_rows) == 1:
                        lookup_row = matching_rows.index[0]
                        lookup_col = df.columns.get_loc(table_array_cols[0])
                        lookup_value = get_cell_reference(lookup_row, lookup_col)
                    else:
                        st.write(f"Multiple occurrences found for value '{lookup_value}':")
                        options = []
                        for idx, row in matching_rows.iterrows():
                            options.append(f"Row {idx + 1}: {', '.join(str(val) for val in row.values)}")
                        selected_option = st.radio("Select the row to use:", options)
                        selected_row = int(selected_option.split(":")[0].split(" ")[1]) - 1
                        lookup_row = matching_rows.index[selected_row]
                        lookup_col = df.columns.get_loc(table_array_cols[0])
                        lookup_value = get_cell_reference(lookup_row, lookup_col)
                else:
                    st.warning(f"No matching value found for '{lookup_value}'. Please enter a valid lookup value.")
                    lookup_value = None
            else:
                st.warning("Please select at least one column for the table array.")
                lookup_value = None
        else:
            child_formula = st.selectbox("Select child formula:", options=["SUM", "VLOOKUP", "MATCH", "INDEX", "AVG"])
            child_target_cell = st.text_input("Enter the target cell for child formula:")
            input_values['lookup_value'] = (child_formula, child_target_cell)
            input_values[child_formula] = {}  # Create a nested dictionary for child formula inputs

        table_array_cols = st.multiselect("Select the table array columns:", options=df.columns.tolist())
        input_values['table_array'] = table_array_cols

        col_index_num = st.number_input("Enter the column index number:", min_value=1, value=1, step=1)
        input_values['col_index_num'] = col_index_num

        range_lookup = st.selectbox("Enter the range lookup:", options=["True", "False"], index=0)
        input_values['range_lookup'] = range_lookup
    elif formula_choice == "MATCH":
        lookup_value_type = st.selectbox("Select lookup value type:", options=["Value", "Formula"])
        if lookup_value_type == "Value":
            lookup_value = st.text_input("Enter the lookup value:")
            input_values['lookup_value'] = lookup_value

            if table_array_cols:
                matching_rows = df[df[table_array_cols[0]] == lookup_value]
                if not matching_rows.empty:
                    if len(matching_rows) == 1:
                        lookup_row = matching_rows.index[0]
                        lookup_col = df.columns.get_loc(table_array_cols[0])
                        lookup_value = get_cell_reference(lookup_row, lookup_col)
                    else:
                        st.write(f"Multiple occurrences found for value '{lookup_value}':")
                        options = []
                        for idx, row in matching_rows.iterrows():
                            options.append(f"Row {idx + 1}: {', '.join(str(val) for val in row.values)}")
                        selected_option = st.radio("Select the row to use:", options)
                        selected_row = int(selected_option.split(":")[0].split(" ")[1]) - 1
                        lookup_row = matching_rows.index[selected_row]
                        lookup_col = df.columns.get_loc(table_array_cols[0])
                        lookup_value = get_cell_reference(lookup_row, lookup_col)
                else:
                    st.warning(f"No matching value found for '{lookup_value}'. Please enter a valid lookup value.")
                    lookup_value = None
            else:
                st.warning("Please select at least one column for the table array.")
                lookup_value = None
        else:
            child_formula = st.selectbox("Select child formula:", options=["SUM", "VLOOKUP", "MATCH", "INDEX", "AVG"])
            child_target_cell = st.text_input("Enter the target cell for child formula:")
            input_values['lookup_value'] = (child_formula, child_target_cell)
            input_values[child_formula] = {}  # Create a nested dictionary for child formula inputs

        table_array_cols = st.multiselect("Select the table array columns:", options=df.columns.tolist())
        input_values['table_array'] = table_array_cols

        match_type = st.selectbox("Enter the match type:", options=[0, -1, 1])
        input_values[
            'match_type'] = match_type  # Create a nested dictionary for child formula inputs  # Create a nested dictionary for child formula inputs
    elif formula_choice == "INDEX":
        array = st.text_input("Enter the array range:")
        input_values['array'] = array

        row_num = st.text_input("Enter the row number:")
        input_values['row_num'] = row_num

        col_num = st.text_input("Enter the column number (optional):")
        input_values['col_num'] = col_num  # Create a nested dictionary for child formula inputs

    # Ask the user for the target cell
    target_cell = st.text_input("Enter the target cell (e.g., 'D1')")

    if st.button("Apply Formula"):
        apply_formula(formula_choice, input_values, target_cell)
