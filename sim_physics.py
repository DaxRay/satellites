import math
import sim_settings as s


def rad(a):
    return math.radians(a)


def satellite(t):
    # Круговая орбита в инерциальных координатах, затем вращение Земли.
    r = s.earth_radius_km + s.orbit_height_km
    u = rad(s.orbit_phase_deg) + math.sqrt(s.earth_mu / r**3) * t
    inc = rad(s.orbit_inclination_deg)
    node = rad(s.orbit_node_deg) - s.earth_rotation * t
    x = r * (math.cos(node)*math.cos(u) - math.sin(node)*math.sin(u)*math.cos(inc))
    y = r * (math.sin(node)*math.cos(u) + math.cos(node)*math.sin(u)*math.cos(inc))
    z = r * math.sin(u)*math.sin(inc)

    lat, lon = rad(s.station_lat_deg), rad(s.station_lon_deg)
    dx = x - s.earth_radius_km * math.cos(lat)*math.cos(lon)
    dy = y - s.earth_radius_km * math.cos(lat)*math.sin(lon)
    dz = z - s.earth_radius_km * math.sin(lat)
    east = -math.sin(lon)*dx + math.cos(lon)*dy
    north = -math.sin(lat)*math.cos(lon)*dx - math.sin(lat)*math.sin(lon)*dy + math.cos(lat)*dz
    up = math.cos(lat)*math.cos(lon)*dx + math.cos(lat)*math.sin(lon)*dy + math.sin(lat)*dz
    distance = math.sqrt(east**2 + north**2 + up**2)
    az = math.degrees(math.atan2(east, north)) % 360
    el = math.degrees(math.atan2(up, math.hypot(east, north)))
    return {'az': az, 'el': el, 'range': distance,
            'visible': el >= s.minimum_elevation_deg,
            'vector': (north/distance, east/distance, up/distance)}


def beam(a, b):
    # Приближённая модель двух эффективных отклонений в угловой плоскости.
    # Для реальных призм нужна калибровка или преломление на каждой поверхности.
    x = s.prism1_deg*math.cos(rad(a)) + s.prism2_deg*math.cos(rad(b))
    y = s.prism1_deg*math.sin(rad(a)) + s.prism2_deg*math.sin(rad(b))
    angle = math.hypot(x, y)
    if angle < 1e-12:
        return (0, 0, 1)
    return (math.sin(rad(angle))*x/angle, math.sin(rad(angle))*y/angle, math.cos(rad(angle)))


def error(a, b, sat):
    ray = beam(a, b)
    dot = sum(ray[i]*sat['vector'][i] for i in range(3))
    return math.degrees(math.acos(max(-1, min(1, dot))))


def power(a, b, sat):
    if not sat['visible']:
        return s.floor_dbm
    # Потери свободного пространства: км, ГГц, дБ.
    loss = 92.45 + 20*math.log10(sat['range']) + 20*math.log10(s.frequency_ghz)
    pointing_loss = 12 * (error(a, b, sat)/s.beam_width_deg)**2
    h = s.eirp_dbw + 30 + s.antenna_gain_dbi - loss - s.other_loss_db - pointing_loss
    return max(s.floor_dbm, h)


def reachable(sat):
    angle = 90-sat['el']
    return sat['visible'] and abs(s.prism1_deg-s.prism2_deg) <= angle <= s.prism1_deg+s.prism2_deg


def validate():
    positive = ['step_deg', 'step_seconds', 'turn_seconds', 'measure_seconds', 'python_line_seconds', 'beam_width_deg',
                'disk_gap_m', 'disk_radius_m', 'frequency_ghz', 'orbit_height_km',
                'earth_radius_km', 'earth_mu', 'flight_seconds', 'search_limit_seconds',
                'speed', 'wall_timeout_seconds', 'sample_seconds']
    for name in positive:
        value = getattr(s, name)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(name + ' должно быть положительным конечным числом')
    for name in ['noise_db', 'prism1_deg', 'prism2_deg']:
        if not math.isfinite(getattr(s, name)) or getattr(s, name) < 0:
            raise ValueError(name + ' не может быть отрицательным')
    if s.prism1_deg+s.prism2_deg >= 90:
        raise ValueError('Сумма отклонений призм должна быть меньше 90°')
    if not (-90 <= s.station_lat_deg <= 90 and 0 <= s.minimum_elevation_deg < 90):
        raise ValueError('Проверь широту станции и маску горизонта')
    for name, value in vars(s).items():
        if isinstance(value, (int, float)) and not math.isfinite(value):
            raise ValueError(name + ' должно быть конечным числом')
    if s.motor_mode not in ('auto', 'step', 'continuous'):
        raise ValueError('motor_mode: выбери auto, step или continuous')
