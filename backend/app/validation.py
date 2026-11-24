from fastapi import HTTPException


KINDS = {
    "missing": "Completa este campo obligatorio.",
    "extra_forbidden": "Este campo no está disponible para esta operación.",
    "uuid_parsing": "Selecciona un registro válido.",
    "uuid_type": "Selecciona un registro válido.",
    "date_from_datetime_parsing": "Introduce una fecha válida.",
    "datetime_from_date_parsing": "Introduce una fecha y hora válidas.",
    "decimal_parsing": "Introduce un número válido.",
    "float_parsing": "Introduce un número válido.",
    "int_parsing": "Introduce un número entero.",
    "int_from_float": "Introduce un número entero.",
    "decimal_max_places": "Reduce el número de decimales.",
    "decimal_max_digits": "El número tiene demasiados dígitos.",
    "literal_error": "Selecciona una opción válida.",
    "string_pattern_mismatch": "Usa el formato indicado para este campo.",
}


def problem(field, detail, status=422):
    return HTTPException(status, detail={"message": detail, "fields": {field: detail}})


def translate(item):
    kind = item["type"]
    context = item.get("ctx", {})
    if kind in {"greater_than", "greater_than_equal"}:
        return "El valor debe ser mayor que " + str(context["gt"]) + "." if "gt" in context else f"El mínimo es {context['ge']}."
    if kind in {"less_than", "less_than_equal"}:
        return "El valor debe ser menor que " + str(context["lt"]) + "." if "lt" in context else f"El máximo es {context['le']}."
    if kind in {"string_too_short", "string_too_long"}:
        return f"Introduce al menos {context['min_length']} caracteres." if "min_length" in context else f"Usa hasta {context['max_length']} caracteres."
    if kind == "value_error":
        message = str(context.get("error", ""))
        if message.startswith(("Usa ", "Registra ", "Selecciona ", "Completa ", "El ", "La ", "Cada ", "Las ", "Los ")):
            return message
        if "IP" in message:
            return "Introduce una dirección IP válida."
        if "email" in message:
            return "Introduce un correo válido."
    return KINDS.get(kind, "Revisa el valor ingresado.")


def fields_for(errors):
    fields = {}
    general = []
    for item in errors:
        loc = tuple(str(part) for part in item["loc"][1:])
        message = translate(item)
        if item["type"] == "value_error" and not loc:
            target = next((field for phrase, field in (
                ("latitud y longitud", "longitude"), ("umbral de aviso", "loss_warning_pct"),
                ("usuario PPPoE", "pppoe_username"), ("asignación fija", "ip_assignment"),
                ("dirección del cliente", "address.address"),
            ) if phrase in message), None)
            if target:
                loc = (target,)
        if loc:
            fields.setdefault(".".join(loc), message)
        elif message not in general:
            general.append(message)
    return fields, general
