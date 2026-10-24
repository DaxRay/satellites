import math
import multiprocessing as mp
import time
import json
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

import sim_settings as s
import sim_physics as p
from sim_runner import run

bg = '#0b1220'
panel = '#131f32'
white = '#e2eaf5'
blue = '#55bfff'
green = '#67edb4'
orange = '#ffbd69'
yaw, pitch = -55, 24
mouse = None
process = None
connection = None
state = None
result = None
samples = []
search_result = None
last_message = 0
path = Path(__file__).with_name('main.py')


def rad(a):
    return math.radians(a)


# Функции рисунка ниже работают только с изображением, а не с main.
def project(p):
    x, y, z = p
    u = x * math.cos(rad(yaw)) - y * math.sin(rad(yaw))
    v = x * math.sin(rad(yaw)) + y * math.cos(rad(yaw))
    depth = v * math.cos(rad(pitch)) - z * math.sin(rad(pitch))
    height = v * math.sin(rad(pitch)) + z * math.cos(rad(pitch))
    scale = min(scene.winfo_width() / 10, scene.winfo_height() / 7)
    return (scene.winfo_width() * 0.5 + u * scale,
            scene.winfo_height() * 0.83 - height * scale, depth)


def line(points, color, width=2, dash=None):
    coords = []
    for p in points:
        coords.extend(project(p)[:2])
    scene.create_line(*coords, fill=color, width=width, dash=dash)


def label(p, text, color):
    x, y, _ = project(p)
    scene.create_text(x + 12, y, text=text, fill=color, anchor='w', font=('Segoe UI', 10))


def disk(z, angle, fill, wedge=False):
    # Клин показан схематически. Толщина специально увеличена для наглядности.
    bottom, top = [], []
    for i in range(64):
        a = i * 2 * math.pi / 64
        x, y = math.cos(a), math.sin(a)
        thickness = 0.12
        if wedge:
            thickness += 0.16 * (1 + x*math.cos(rad(angle)) + y*math.sin(rad(angle)))
        bottom.append((x, y, z))
        top.append((x, y, z + thickness))
    faces = [bottom, top]
    for i in range(64):
        j = (i + 1) % 64
        faces.append([bottom[i], bottom[j], top[j], top[i]])
    faces.sort(key=lambda face: sum(project(p)[2] for p in face)/len(face), reverse=True)
    for face in faces:
        coords = []
        for p in face:
            coords.extend(project(p)[:2])
        scene.create_polygon(*coords, fill=fill, outline='#446078', width=1)
    if wedge:
        line([(0, 0, z + 0.5), (0.9*math.cos(rad(angle)), 0.9*math.sin(rad(angle)), z+0.5)], white, 4)


def draw_scene():
    scene.delete('all')
    if state is None:
        return
    a, b = state['phig1'], state['phig2']
    gap = s.disk_gap_m / s.disk_radius_m
    for i in range(-3, 4):
        line([(i, -3, 0), (i, 3, 0)], '#213149', 1)
        line([(-3, i, 0), (3, i, 0)], '#213149', 1)
    line([(0, 0, 0), (0, 0, 5)], '#45556b', 1, (4, 5))
    disk(0.1, 0, '#283e55')
    disk(0.1 + gap, a, '#22789c', True)
    disk(0.1 + 2*gap, b, '#98713b', True)
    label((1.1, 0, 0.2), 'Антенна', '#a6b8cc')
    label((1.1, 0, 0.3 + gap), f'Призма 1: {a % 360:.1f}°', blue)
    label((1.1, 0, 0.3 + 2*gap), f'Призма 2: {b % 360:.1f}°', orange)
    origin = (0, 0, 0.65 + 2*gap)
    ray = p.beam(a, b)
    end = tuple(origin[i] + 3*ray[i] for i in range(3))
    line([origin, end], blue, 4)
    label(end, 'Луч', blue)
    if state['sat']['visible']:
        target = tuple(origin[i] + 3*state['sat']['vector'][i] for i in range(3))
        line([origin, target], green, 2, (6, 5))
        x, y, _ = project(target)
        scene.create_rectangle(x-24, y-6, x+24, y+6, fill='#31739c', outline=green)
        scene.create_rectangle(x-6, y-10, x+6, y+10, fill=white, outline=green)
        scene.create_text(x, y-23, text='СПУТНИК', fill=green, font=('Segoe UI', 10, 'bold'))
    else:
        scene.create_text(20, 78, anchor='nw', text='Спутник скрыт за горизонтом', fill=orange, font=('Segoe UI', 12))
    scene.create_text(20, 18, anchor='nw', text='3D • потяни мышью, чтобы повернуть', fill='#9badc4', font=('Segoe UI', 11))
    scene.create_text(20, 44, anchor='nw', text='Геометрия призм условная; дальность спутника не в масштабе', fill='#8295af', font=('Segoe UI', 9))
    # Вид сверху: две стрелки и их сумма помогают понять работу пары.
    cx, cy = scene.winfo_width()-100, 115
    k = 45/max(1, s.prism1_deg+s.prism2_deg)
    scene.create_text(cx, 65, text='Призмы → луч', fill='#95a9c3', font=('Segoe UI', 9))
    scene.create_oval(cx-45, cy-45, cx+45, cy+45, outline='#33445d')
    dx = dy = 0
    for angle, size, col in [(a, s.prism1_deg, blue), (b, s.prism2_deg, orange)]:
        x, y = size*math.sin(rad(angle))*k, -size*math.cos(rad(angle))*k
        scene.create_line(cx, cy, cx+x, cy+y, fill=col, width=3, arrow='last')
        dx, dy = dx+x, dy+y
    scene.create_line(cx, cy, cx+dx, cy+dy, fill=green, width=2, arrow='last')
    scene.create_text(cx, cy+57, text='Синяя — призма 1\nОранжевая — призма 2\nЗелёная — итоговый луч', fill='#95a9c3', font=('Segoe UI', 8))


def sky_point(sat):
    w, h = sky.winfo_width(), sky.winfo_height()
    r = min(w, h)*0.37
    k = (90-sat['el'])/90
    return (w/2 + r*k*math.sin(rad(sat['az'])), h/2-r*k*math.cos(rad(sat['az'])))


def draw_sky():
    sky.delete('all')
    w, h = sky.winfo_width(), sky.winfo_height()
    cx, cy, r = w/2, h/2, min(w, h)*0.37
    for el in (0, 30, 60):
        rr = r*(90-el)/90
        sky.create_oval(cx-rr, cy-rr, cx+rr, cy+rr, outline='#35455e')
        sky.create_text(cx+rr-12, cy+10, text=f'{el}°', fill='#7d91aa', font=('Segoe UI', 8))
    sky.create_line(cx-r, cy, cx+r, cy, fill='#29394f')
    sky.create_line(cx, cy-r, cx, cy+r, fill='#29394f')
    for x, y, text in [(cx, cy-r-14, 'С / 0°'), (cx+r+20, cy, 'В'), (cx, cy+r+15, 'Ю'), (cx-r-20, cy, 'З')]:
        sky.create_text(x, y, text=text, fill=white, font=('Segoe UI', 9))
    # Поле наведения горизонтальной платформы.
    rr = r*(s.prism1_deg+s.prism2_deg)/90
    sky.create_oval(cx-rr, cy-rr, cx+rr, cy+rr, outline=orange, dash=(3, 4))
    inner = r*abs(s.prism1_deg-s.prism2_deg)/90
    if inner > 1:
        sky.create_oval(cx-inner, cy-inner, cx+inner, cy+inner, outline=orange, dash=(3, 4))
    sky.create_text(cx, cy+5, text='90°', fill='#95a9c3', anchor='n', font=('Segoe UI', 8))
    prev = None
    for i in range(241):
        sat = p.satellite(s.start_orbit_seconds + i*s.flight_seconds/240)
        xy = sky_point(sat)
        if sat['visible'] and prev:
            sky.create_line(*prev, *xy, fill='#315e64', width=2)
        prev = xy if sat['visible'] else None
    if state:
        if state['sat']['visible']:
            x, y = sky_point(state['sat'])
            sky.create_oval(x-5, y-5, x+5, y+5, fill=green, outline=green)
        ray = p.beam(state['phig1'], state['phig2'])
        az = math.degrees(math.atan2(ray[1], ray[0])) % 360
        el = math.degrees(math.asin(max(-1, min(1, ray[2]))))
        x, y = sky_point({'az': az, 'el': el})
        sky.create_line(x-6, y, x+6, y, fill=blue, width=2)
        sky.create_line(x, y-6, x, y+6, fill=blue, width=2)


def draw_orbit():
    orbit.delete('all')
    w, h = orbit.winfo_width(), orbit.winfo_height()
    def xy(t, el):
        return 40 + (w-55)*t/s.flight_seconds, 16 + (h-42)*(90-el)/120
    for el in (-30, 0, 30, 60, 90):
        x, y = xy(0, el)
        orbit.create_line(x, y, w-15, y, fill='#304058')
        orbit.create_text(20, y, text=str(el), fill='#95a9c3', font=('Segoe UI', 8))
    points = []
    for i in range(241):
        t = i*s.flight_seconds/240
        el = p.satellite(s.start_orbit_seconds+t)['el']
        points.extend(xy(t, max(-30, el)))
    orbit.create_line(*points, fill=green, width=2)
    if state:
        t = state['seconds'] if state['phase'] == 'flight' else 0
        x, y = xy(t, max(-30, state['sat']['el']))
        orbit.create_line(x, 12, x, h-24, fill=orange, dash=(4, 4))
        if state['sat']['visible']:
            orbit.create_oval(x-4, y-4, x+4, y+4, fill=green)
    for t in (0, s.flight_seconds/2, s.flight_seconds):
        x, _ = xy(t, 0)
        orbit.create_text(x, h-10, text=f'{t:.0f} с', fill='#95a9c3', font=('Segoe UI', 9))


def draw_signal():
    graph.delete('all')
    w = graph.winfo_width()
    low, high = s.floor_dbm, max(-50, s.link_threshold_dbm+10)
    def yy(h):
        return 12+85*(high-max(low, min(high, h)))/(high-low)
    for h in (low, s.link_threshold_dbm, high):
        y = yy(h)
        graph.create_line(45, y, w-15, y, fill=orange if h == s.link_threshold_dbm else '#304058', dash=(3, 4))
        graph.create_text(22, y, text=f'{h:.0f}', fill='#95a9c3', font=('Segoe UI', 8))
    if len(samples) > 1:
        t0, t1 = samples[0][0], samples[-1][0]
        coords = []
        for t, value in samples:
            coords.extend((45+(w-60)*(t-t0)/max(1e-9, t1-t0), yy(value)))
        graph.create_line(*coords, fill=blue, width=2)
        graph.create_text(48, 110, text=f'{t0:.1f} с', fill='#95a9c3', anchor='w')
        graph.create_text(w-15, 110, text=f'{t1:.1f} с', fill='#95a9c3', anchor='e')


def draw():
    if not state:
        return
    draw_scene()
    draw_sky()
    draw_orbit()
    draw_signal()
    sat = state['sat']
    name = '1 / Поиск • спутник заморожен' if state['phase'] == 'search' else '2 / Сопровождение • спутник летит'
    mode = {'step': 'пошаговый', 'continuous': 'непрерывный'}.get(state.get('motor_mode'), 'определение режима')
    phase_text.set(f'{name}    |    t = {state["seconds"]:.2f} с    |    {mode}')
    power_text.set(f'{state["power"]:.1f} дБм   •   ошибка {state["error"]:.2f}°')
    zone = 'доступен для наведения' if state['reachable'] else ('виден, вне поля наведения' if sat['visible'] else 'за горизонтом')
    position_text.set(f'Азимут {sat["az"]:.1f}°  |  Высота {sat["el"]:.1f}°  |  {sat["range"]:.0f} км\n{zone}')
    counts.set(f'Измерений A(): {state["measurements"]:,}  •  команд движения: {state["moves"]:,}'.replace(',', ' '))


def search_text(r):
    lines = ['ЭТАП 1. НЕПОДВИЖНЫЙ СПУТНИК',
             f'Время алгоритма: {r["seconds"]:.2f} с ({r["seconds"]/60:.1f} мин).',
             f'Измерений: {r["measurements"]}; команд движения: {r["moves"]}.']
    if r.get('motor_mode'):
        lines.insert(1, 'Привод: ' + ('пошаговый' if r['motor_mode'] == 'step' else 'непрерывный'))
    if r['answer']:
        h, a, b = r['answer']
        lines.append(f'Твой ответ: A = {h:.3f}; углы {a:.3f}° / {b:.3f}°.')
        lines.append(f'Проверка этих углов без шума: {r["answer_power"]:.3f} дБм; ошибка {r["answer_error"]:.3f}°.')
        if r['gap_db'] is not None:
            quality = 'Хорошее наведение' if r['gap_db'] <= 0.5 else 'Можно найти лучше'
            lines.append(f'{quality}: отставание от максимума на сетке — {r["gap_db"]:.3f} дБ.')
        if not r['on_step_grid']:
            lines.append('Углы взяты во время непрерывного вращения; сравнение с сеткой — ориентир.')
    else:
        lines.append('Ответ не получен. Поддерживаются return Ans/словарь/тройка или print(h, phig1, phig2).')
    if r['measurements'] == 0:
        lines.append('Алгоритм ни разу не вызвал A(): поиска по сигналу не было. Проверь условия входа в циклы.')
    lines.append(f'Фактический сигнал в конце поиска: {r["actual_power"]:.2f} дБм.')
    if r['answer'] and r['answer_power']-r['actual_power'] > 1:
        lines.append('Код нашёл углы, но не установил в них антенну: вывод ответа сам по себе не двигает диски.')
    if r['angle_mismatches']:
        lines.append(f'Несовпадений счётчиков main с механизмом: {r["angle_mismatches"]}. Проверь шаг и ручные +=.')
    if r['ended'] == 'time_limit':
        lines.append('Поиск остановлен лимитом модельного времени.')
    return '\n'.join(lines)


def report_text(r):
    f = r['flight']
    initial = 'Углы второго этапа — те, на которых твой код закончил поиск. Стенд их не переставляет.'
    lines = [search_text(r['search']), '', 'ЭТАП 2. ДВИЖУЩИЙСЯ СПУТНИК', initial,
             f'Вызвано из main.py: {f["function"]}. Проверено {f["seconds"]:.1f} с полёта.',
             f'Над горизонтом: {f["visible_seconds"]:.1f} с; в поле наведения призм: {f["reachable_seconds"]:.1f} с.']
    if f['linked_percent'] is None:
        lines.append('Оценка сопровождения невозможна: спутник не входил в поле наведения.')
    else:
        quality = 'Хорошее сопровождение' if f['linked_percent'] >= 95 else ('Связь удерживается частично' if f['linked_percent'] >= 50 else 'Сопровождение не удерживает связь')
        lines += [f'{quality}: связь {f["linked_percent"]:.2f}% доступного времени.',
                  f'Связь за всё время видимости: {f["visible_linked_percent"]:.2f}%.',
                  f'Среднеквадратичная ошибка в поле наведения: {f["rms_error"]:.2f}°.',
                  f'Самая долгая потеря связи в поле наведения: {f["longest_loss"]:.1f} с.']
    if f['returned_at'] is not None:
        lines.append(f'Файл завершился на {f["returned_at"]:.2f} с полёта. Далее исполнялись только уже запущенные движения.')
    if not f.get('controller_seen', True):
        lines.append('Выполнение файла не дошло до real_time()/track(). Эмулятор не запускает их за тебя.')
    if r.get('signal_from_main'):
        lines.append('Включена исходная A() из main. Она может не соответствовать физическому сигналу; оценка ниже относится к геометрии луча.')
    if r.get('error'):
        lines += ['', 'ОШИБКА ПРИ ВЫПОЛНЕНИИ main.py', r['error']]
    if f['angle_mismatches']:
        lines.append(f'Несовпадений углов main с механизмом: {f["angle_mismatches"]}.')
    lines += ['', 'Оценка: без измерительного шума, с шагом времени sample_seconds.',
              'Граница «хорошо»: поиск ≤ 0.5 дБ от максимума; сопровождение ≥ 95% времени связи.',
              'Это критерии этого стенда. Нет модели ускорения, люфта, пропуска шагов, атмосферы и точной геометрии призм.']
    return '\n'.join(lines)


def set_report(text):
    report_box.configure(state='normal')
    report_box.delete('1.0', 'end')
    report_box.insert('1.0', text)
    report_box.configure(state='disabled')


def stop():
    global process, connection
    if process is not None:
        if process.is_alive():
            process.terminate()
        process.join(timeout=1)
        process.close()
        process = None
    if connection is not None:
        connection.close()
        connection = None
    status.set('Проверка остановлена. main.py не изменён.')


def settings_values():
    values = {}
    for name, var in fields.items():
        old = getattr(s, name)
        if isinstance(old, bool):
            value = bool(var.get())
        elif isinstance(old, str):
            value = var.get().strip()
        else:
            value = float(var.get().replace(',', '.'))
            if isinstance(old, int):
                if not value.is_integer():
                    raise ValueError(name + ' должно быть целым числом')
                value = int(value)
        values[name] = value
    old = {name: getattr(s, name) for name in values}
    try:
        for name, value in values.items():
            setattr(s, name, value)
        p.validate()
    except Exception:
        for name, value in old.items():
            setattr(s, name, value)
        raise
    return values


def start():
    global process, connection, acceleration, state, result, samples, search_result, last_message
    stop()
    try:
        values = settings_values()
        if not path.exists():
            raise ValueError(f'Не найден файл {path}')
    except Exception as exc:
        messagebox.showerror('Параметры', str(exc))
        return
    result, search_result, samples = None, None, []
    state = {'phase': 'search', 'seconds': 0, 'phig1': 0, 'phig2': 0,
             'sat': p.satellite(s.start_orbit_seconds), 'power': s.floor_dbm,
             'error': 0, 'measurements': 0, 'moves': 0, 'reachable': True}
    set_report('Запущен твой main.py. Здесь появится проверка его ответа и качества сопровождения.')
    context = mp.get_context('spawn')
    connection, child = context.Pipe(duplex=False)
    acceleration = context.Value('d', float(speed_scale.get()))
    process = context.Process(target=run, args=(str(path), child, acceleration, values))
    process.start()
    child.close()
    last_message = time.monotonic()
    status.set('Выполняется весь main.py, включая нижний блок запуска. Управление — из твоего файла.')
    tabs.select(observe)
    draw()


def poll():
    global state, result, samples, search_result, last_message, connection
    changed = False
    if process is not None:
        acceleration.value = float(speed_scale.get())
    if connection is not None:
        try:
            # Ограничиваем чтение, чтобы даже печатающий в цикле main не заморозил окно.
            for _ in range(100):
                if not connection.poll():
                    break
                kind, value = connection.recv()
                if kind != 'log':
                    last_message = time.monotonic()
                if kind == 'frame':
                    if state and state['phase'] != value['phase']:
                        samples = []
                    state = value
                    samples.append((value['seconds'], value['power']))
                    samples = samples[-600:]
                    changed = True
                elif kind == 'search_result':
                    search_result = value
                    set_report(search_text(value) + '\n\nИдёт второй этап — сопровождение.')
                elif kind == 'done':
                    result = value
                    set_report(report_text(value))
                    status.set('Проверка завершена. ' + ('В main.py обнаружена ошибка — смотри отчёт.' if value.get('error') else 'Итоги находятся на вкладке «Отчёт».'))
                elif kind == 'error':
                    set_report('Ошибка в проверяемом коде или настройках:\n\n' + value)
                    status.set('Проверка завершилась ошибкой — подробности в отчёте.')
        except (EOFError, OSError):
            connection.close()
            connection = None
            if result is None:
                status.set('Процесс завершён без полного результата. Смотри отчёт.')
    if process is not None and process.is_alive() and time.monotonic()-last_message > s.wall_timeout_seconds:
        stop()
        set_report('Код слишком долго не обращался к A()/move1()/move2(). Проверка остановлена по тайм-ауту.')
    if changed:
        draw()
    root.after(40, poll)


def save_report():
    if result is None:
        messagebox.showinfo('Отчёт', 'Сначала дождись завершения проверки.')
        return
    name = Path(__file__).with_name('simulation_report.json')
    name.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    name.with_suffix('.txt').write_text(report_text(result), encoding='utf-8')
    status.set('Сохранены simulation_report.json и simulation_report.txt рядом с emulator.py.')


def mouse_down(event):
    global mouse
    mouse = (event.x, event.y)


def mouse_move(event):
    global mouse, yaw, pitch
    if mouse:
        yaw += (event.x-mouse[0])*0.5
        pitch = max(5, min(75, pitch+(event.y-mouse[1])*0.3))
        mouse = (event.x, event.y)
        draw_scene()


def close():
    stop()
    root.destroy()


def main():
    global root, scene, sky, orbit, graph, tabs, observe, report_box, fields
    global status, phase_text, power_text, position_text, counts, speed_scale
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    root = tk.Tk()
    root.title('Рисли • проверка main.py')
    root.geometry(f'{min(1260, root.winfo_screenwidth()-60)}x{min(850, root.winfo_screenheight()-100)}+20+20')
    root.minsize(1000, 740)
    root.configure(bg=bg)
    style = ttk.Style()
    style.theme_use('clam')
    style.configure('TButton', padding=7, background='#263b56', foreground=white)
    style.configure('TNotebook', background=bg, borderwidth=0)
    style.configure('TNotebook.Tab', background='#263b56', foreground=white, padding=(16, 8))
    style.map('TNotebook.Tab', background=[('selected', '#387395')])
    tk.Label(root, text='РИСЛИ / Испытание алгоритма', bg=bg, fg=white, font=('Segoe UI', 20, 'bold')).pack(anchor='w', padx=18, pady=(12, 4))
    controls = tk.Frame(root, bg=bg)
    controls.pack(fill='x', padx=18, pady=4)
    for text, command in [('Перезапустить main.py', start), ('Остановить', stop), ('Сохранить отчёт', save_report)]:
        ttk.Button(controls, text=text, command=command).pack(side='left', padx=(0, 8))
    tk.Label(controls, text='Ускорение показа ×', bg=bg, fg=white).pack(side='left')
    speed_scale = tk.Scale(controls, from_=1, to=1000, orient='horizontal', bg=bg, fg=white, highlightthickness=0, length=210)
    speed_scale.set(s.speed)
    speed_scale.pack(side='left')
    tabs = ttk.Notebook(root)
    tabs.pack(fill='both', expand=True, padx=18, pady=8)
    observe, settings_tab, report_tab = [tk.Frame(tabs, bg=panel) for _ in range(3)]
    for frame, name in [(observe, 'Наблюдение'), (settings_tab, 'Настройки'), (report_tab, 'Отчёт')]:
        tabs.add(frame, text=name)
    phase_text, power_text, position_text, counts, status = [tk.StringVar() for _ in range(5)]
    tk.Label(observe, textvariable=phase_text, bg=panel, fg=orange, font=('Segoe UI', 13)).pack(pady=8)
    body = tk.Frame(observe, bg=panel)
    body.pack(fill='both', expand=True)
    left = tk.Frame(body, bg=panel)
    left.pack(side='left', fill='both', expand=True)
    right = tk.Frame(body, bg=panel, width=390)
    right.pack(side='right', fill='y')
    scene = tk.Canvas(left, height=100, width=100, bg=panel, highlightthickness=0)
    scene.pack(fill='both', expand=True)
    scene.bind('<Button-1>', mouse_down)
    scene.bind('<B1-Motion>', mouse_move)
    scene.bind('<Configure>', lambda e: draw_scene())
    tk.Label(left, textvariable=power_text, bg=panel, fg=blue, font=('Segoe UI', 19)).pack()
    tk.Label(left, text='Сигнал без шума • пунктир — порог связи • время текущего этапа', bg=panel, fg='#95a9c3').pack(pady=3)
    graph = tk.Canvas(left, height=125, bg=panel, highlightthickness=0)
    graph.pack(fill='x')
    tk.Label(right, text='ПОЛОЖЕНИЕ НА НЕБЕ', bg=panel, fg=white, font=('Segoe UI', 12, 'bold')).pack()
    sky = tk.Canvas(right, width=390, height=210, bg=panel, highlightthickness=0)
    sky.pack(fill='both', expand=True)
    tk.Label(right, text='Зелёная точка — спутник. Синий крест — луч.\nВнешний круг — горизонт. Центр — над головой.\nОранжевый пунктир — граница наведения:\nспутник внутри → призмы могут на него навестись.', bg=panel, fg='#95a9c3', justify='left', font=('Segoe UI', 9)).pack()
    tk.Label(right, textvariable=position_text, bg=panel, fg=green, font=('Segoe UI', 10)).pack(pady=8)
    tk.Label(right, text='ВЫСОТА НАД ГОРИЗОНТОМ / ВРЕМЯ ПОЛЁТА', bg=panel, fg=white, font=('Segoe UI', 10)).pack()
    orbit = tk.Canvas(right, width=390, height=160, bg=panel, highlightthickness=0)
    orbit.pack(fill='x')
    tk.Label(observe, textvariable=counts, bg=panel, fg='#95a9c3').pack(side='bottom', before=body, pady=6)

    tk.Label(settings_tab, text='motor_mode = auto: режим определяется по main.py. step: законченный шаг; continuous: вращение без ожидания.\nВ step move1()/move2() двигают диск на step_deg за step_seconds; оба угла ты считаешь вручную.\nВ continuous заданный угол выполняется за turn_seconds. A() доступна даже без определения в main.py.', bg=panel, fg=white, justify='left').pack(anchor='w', padx=15, pady=10)
    scroll = tk.Canvas(settings_tab, bg=panel, highlightthickness=0)
    scrollbar = ttk.Scrollbar(settings_tab, orient='vertical', command=scroll.yview)
    scrollbar.pack(side='right', fill='y')
    scroll.pack(side='left', fill='both', expand=True)
    scroll.configure(yscrollcommand=scrollbar.set)
    form = tk.Frame(scroll, bg=panel)
    scroll.create_window((0, 0), window=form, anchor='nw')
    form.bind('<Configure>', lambda e: scroll.configure(scrollregion=scroll.bbox('all')))
    fields = {}
    # Комментарии из файла настроек показываем рядом с полями.
    comments = {}
    for line_text in Path(s.__file__).read_text(encoding='utf-8-sig').splitlines():
        if '=' in line_text and '#' in line_text and not line_text.lstrip().startswith('#'):
            comments[line_text.split('=')[0].strip()] = line_text.split('#', 1)[1].strip()
    row = 0
    for name, value in vars(s).items():
        if name.startswith('_') or not isinstance(value, (float, int, bool, str)):
            continue
        tk.Label(form, text=name, bg=panel, fg=blue).grid(row=row, column=0, sticky='w', padx=15, pady=4)
        if isinstance(value, bool):
            var = tk.BooleanVar(value=value)
            widget = tk.Checkbutton(form, variable=var, bg=panel, selectcolor=bg, activebackground=panel)
        elif name == 'motor_mode':
            var = tk.StringVar(value=value)
            widget = ttk.Combobox(form, textvariable=var, values=('auto', 'step', 'continuous'), width=12, state='readonly')
        else:
            var = tk.StringVar(value=str(value))
            widget = tk.Entry(form, textvariable=var, width=13, bg=bg, fg=white, insertbackground=white)
        widget.grid(row=row, column=1, padx=8)
        tk.Label(form, text=comments.get(name, ''), bg=panel, fg=white, wraplength=560, justify='left').grid(row=row, column=2, sticky='w', padx=8)
        fields[name] = var
        row += 1
    report_box = tk.Text(report_tab, wrap='word', bg=panel, fg=white, padx=18, pady=15, font=('Segoe UI', 11), relief='flat')
    report_scroll = ttk.Scrollbar(report_tab, orient='vertical', command=report_box.yview)
    report_scroll.pack(side='right', fill='y')
    report_box.configure(yscrollcommand=report_scroll.set)
    report_box.pack(fill='both', expand=True)
    tk.Label(root, textvariable=status, bg=bg, fg=orange, wraplength=1150).pack(side='bottom', before=tabs, pady=(0, 10))
    root.protocol('WM_DELETE_WINDOW', close)
    root.after(40, poll)
    root.after(500, start)
    root.mainloop()


if __name__ == '__main__':
    mp.freeze_support()
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == '--main':
        path = Path(sys.argv[2]).resolve()
    main()

