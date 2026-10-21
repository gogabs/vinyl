"""Como o Vinyl fala números, tempos e velocidades em português."""


def plural(n, one, many):
    return "%d %s" % (n, one if n == 1 else many)


def duration(seconds):
    """1 hora e 20 minutos; 14 minutos; 40 segundos."""
    seconds = max(0, int(seconds or 0))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return plural(hours, "hora", "horas") + (" e " + plural(minutes, "minuto", "minutos") if minutes else "")
    if minutes:
        return plural(minutes, "minuto", "minutos")
    return plural(secs, "segundo", "segundos")


def clock(seconds):
    """Minuto dentro de um capítulo: "14 minutos" ou "1 hora e 2 minutos"; "começo" abaixo de 1 min."""
    if (seconds or 0) < 60:
        return "começo" if (seconds or 0) < 5 else duration(seconds)
    return duration(seconds)


def speed(value):
    """1,25 vezes."""
    text = ("%.2f" % value).rstrip("0").rstrip(".").replace(".", ",")
    return "%s vezes" % text


def percent(fraction):
    return "%d%%" % int(round(max(0.0, min(1.0, fraction)) * 100))
