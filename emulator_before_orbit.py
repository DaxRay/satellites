import math
import tkinter as tk
from tkinter import ttk


# Это учебная модель. Настоящие характеристики призм пока неизвестны.
# Каждая призма отклоняет луч в свою сторону, отклонения складываются.
# Q1 — азимут спутника, Q2 — высота спутника над платформой.

phig1 = 0
phig2 = 0
move = 1
q1 = 40
q2 = 70
otkl = 15             # отклонение от одной призмы, градусы
width = 5             # ширина диаграммы антенны, градусы
distance = 0.65       # расстояние между дисками, условные единицы

running = False
index = 0
count = 360
best_h = -101
best_phig1 = 0
best_phig2 = 0
history = []
yaw = -55
pitch = 24
mouse = None

bg = '#0b1220'
panel = '#131f32'
white = '#e2eaf5'
blue = '#55bfff'
green = '#67edb4'
orange = '#ffbd69'


def rad(angle):
    return math.radians(angle)


def direction(a, b):
    # Модель в плоскости углов: две стрелки отклонения складываются.
    x = otkl * (math.cos(rad(a)) + math.cos(rad(b)))
    y = otkl * (math.sin(rad(a)) + math.sin(rad(b)))
    angle = math.hypot(x, y)
    if angle < 0.000001:
        return (0, 0, 1)
    return (math.sin(rad(angle)) * x / angle,
            math.sin(rad(angle)) * y / angle,
            math.cos(rad(angle)))


def satellite():
    return (math.cos(rad(q2)) * math.cos(rad(q1)),
            math.cos(rad(q2)) * math.sin(rad(q1)),
            math.sin(rad(q2)))


def error():
    ray = direction(phig1, phig2)
    sat = satellite()
    dot = sum(ray[i] * sat[i] for i in range(3))
    return math.degrees(math.acos(max(-1, min(1, dot))))


def A():
    import random

    if not hasattr(A, "table"):
        A.table = {}
        A.used = set()

    # Одна и та же пара углов всегда даёт одно и то же число.
    angles = (round(phig1 % 360, 6) % 360, round(phig2 % 360, 6) % 360)

    if angles not in A.table:
        if len(A.used) == 100_000_001:
            raise RuntimeError("Все уникальные значения сигнала закончились")

        h = random.randint(-100_000_000, 0)
        while h in A.used:
            h = random.randint(-100_000_000, 0)

        A.used.add(h)
        A.table[angles] = h / 1_000_000

    return A.table[angles]


def move1(steps=1):
    global phig1
    phig1 = (phig1 + steps * move) % 360


def move2(steps=1):
    global phig2
    phig2 = (phig2 + steps * move) % 360


def color(h):
    t = (h + 100) / 100
    return '#%02x%02x%02x' % (int(24 + 75*t), int(35 + 200*t), int(65 + 110*t))


def reset():
    global running, index, best_h, history, phig1, phig2
    running = False
    index = 0
    best_h = -101
    history = []
    phig1 = 0
    phig2 = 0
    heat.put(bg, to=(0, 0, 360, 360))
    heat_canvas.delete('marker')
    status.set('Готово к поиску. Можно вращать диски вручную.')
    draw()


def start():
    global running
    if index >= count * count:
        reset()
    running = True
    status.set('Поиск по показаниям A(). Перебираем все пары углов.')


def pause():
    global running
    running = False
    status.set('Пауза. «Поиск» продолжит с того же места.')


def go_best():
    global running, phig1, phig2
    running = False
    if best_h > -101:
        phig1 = best_phig1
        phig2 = best_phig2
        status.set('Диски установлены в лучшее найденное положение.')
        draw()


def manual(disk, steps):
    global running
    running = False
    if disk == 1:
        move1(steps)
    else:
        move2(steps)
    status.set('Ручное вращение. Значение A() меняется вместе с лучом.')
    draw()


def apply():
    global q1, q2, otkl, width, distance, move, count
    try:
        a, b, c, d, e, f = [float(v.get().replace(',', '.')) for v in entries]
        if not all(math.isfinite(v) for v in (a, b, c, d, e, f)):
            raise ValueError
        if not (0 <= b <= 90 and 1 <= c <= 30 and 1 <= d <= 30
                and 0.3 <= e <= 1.3 and 0.5 <= f <= 30):
            raise ValueError
        n = round(360 / f)
        if abs(n * f - 360) > 0.000001:
            status.set('Шаг должен делить 360° без остатка: 0.5, 1, 1.8, 2, 5…')
            return
        q1, q2, otkl, width, distance, move = a % 360, b, c, d, e, f
        count = n
        reset()
        if 90 - q2 > 2 * otkl:
            status.set('Спутник вне зоны наведения. Поиск найдёт лишь лучший доступный сигнал.')
    except ValueError:
        status.set('Проверь числа и диапазоны, указанные рядом с полями.')


def tick():
    global index, phig1, phig2, best_h, best_phig1, best_phig2, running
    if running:
        # Скорость — количество измерений за кадр, не скорость мотора.
        for _ in range(int(speed.get())):
            if index == count * count:
                running = False
                phig1, phig2 = best_phig1, best_phig2
                status.set('Поиск завершён. Найден максимум на выбранной сетке углов.')
                break

            # Обход змейкой: второй двигатель не делает скачок при смене ряда.
            row = index // count
            col = index % count
            if row % 2 == 1:
                col = count - 1 - col
            phig1 = row * move
            phig2 = col * move
            h = A()
            if h > best_h:
                best_h = h
                best_phig1, best_phig2 = phig1, phig2

            x, y = int(phig1), 359 - int(phig2)
            size = max(1, math.ceil(move))
            heat.put(color(h), to=(x, max(0, y-size+1), min(360, x+size), y+1))
            index += 1
        history.append((A(), best_h))
        if len(history) > 500:
            history.pop(0)
        draw()
    root.after(40, tick)


# Простая 3D-проекция. Мышью можно повернуть сцену.
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


def draw():
    global heat_view
    scene.delete('all')
    for i in range(-3, 4):
        line([(i, -3, 0), (i, 3, 0)], '#213149', 1)
        line([(-3, i, 0), (3, i, 0)], '#213149', 1)
    line([(0, 0, 0), (0, 0, 5)], '#45556b', 1, (4, 5))
    label((2.8, 0, 0), 'X', '#718198')
    label((0, 2.8, 0), 'Y', '#718198')
    disk(0.1, 0, '#283e55')
    disk(0.1 + distance, phig1, '#22789c', True)
    disk(0.1 + 2*distance, phig2, '#98713b', True)
    label((1.1, 0, 0.2), 'Антенна', '#a6b8cc')
    label((1.1, 0, 0.3 + distance), 'Призма 1', blue)
    label((1.1, 0, 0.3 + 2*distance), 'Призма 2', orange)

    origin = (0, 0, 0.65 + 2*distance)
    ray = direction(phig1, phig2)
    sat = satellite()
    end = tuple(origin[i] + 3.2 * ray[i] for i in range(3))
    target = tuple(origin[i] + 3.2 * sat[i] for i in range(3))
    # Пунктир показывает направление на спутник от выхода системы.
    # Реальный спутник далеко: расстояния в сцене условные.
    line([origin, target], green, 2, (6, 5))
    line([origin, end], blue, 5)
    label(end, 'Луч', blue)
    x, y, _ = project(target)
    scene.create_rectangle(x-23, y-6, x+23, y+6, fill='#31739c', outline=green)
    scene.create_rectangle(x-6, y-10, x+6, y+10, fill=white, outline=green)
    scene.create_text(x, y-23, text='СПУТНИК', fill=green, font=('Segoe UI', 10, 'bold'))
    scene.create_text(20, 20, anchor='nw', text='3D • потяни мышью, чтобы повернуть', fill='#9badc4', font=('Segoe UI', 11))
    scene.create_text(20, 46, anchor='nw', text='Схематическая модель • масштаб условный', fill='#657c98', font=('Segoe UI', 10))

    signal.set(f'{A():.2f}  усл. дБ')
    angles.set(f'Призма 1: {phig1:.1f}°     Призма 2: {phig2:.1f}°\nОшибка наведения: {error():.2f}°')
    progress.set(f'{index:,} / {count*count:,} положений   •   {100*index/(count*count):.1f}%'.replace(',', ' '))
    best.set('Лучшее положение ещё не найдено' if best_h == -101 else
             f'Максимум: {best_h:.2f}   |   {best_phig1:.1f}° / {best_phig2:.1f}°')
    bar['value'] = 100 * index / (count * count)
    heat_canvas.delete('marker')
    heat_view = heat.zoom(2).subsample(3)
    heat_canvas.itemconfigure('map', image=heat_view)
    x, y = phig1 * 2/3, (359-phig2) * 2/3
    heat_canvas.create_oval(x-4, y-4, x+4, y+4, outline=white, width=2, tags='marker')
    graph.delete('all')
    w = max(100, graph.winfo_width())
    for h in (0, -50, -100):
        y = 12 - h * 0.8
        graph.create_line(35, y, w-10, y, fill='#273750')
        graph.create_text(18, y, text=str(h), fill='#8196b1', font=('Segoe UI', 8))
    if len(history) > 1:
        for j, col in [(0, blue), (1, green)]:
            points = []
            for i, values in enumerate(history):
                points.extend((35 + i*(w-50)/max(1, len(history)-1), 12-values[j]*0.8))
            graph.create_line(*points, fill=col, width=2)


def mouse_down(event):
    global mouse
    mouse = (event.x, event.y)


def mouse_move(event):
    global mouse, yaw, pitch
    if mouse:
        yaw += (event.x-mouse[0]) * 0.5
        pitch = max(5, min(75, pitch + (event.y-mouse[1]) * 0.3))
        mouse = (event.x, event.y)
        draw()


def main():
    global root, scene, heat, heat_canvas, graph, status, speed
    global signal, angles, progress, best, bar, entries
    root = tk.Tk()
    root.title('Рисли • поиск спутника')
    root.geometry('1280x900')
    root.minsize(1080, 820)
    root.configure(bg=bg)
    style = ttk.Style()
    style.theme_use('clam')
    style.configure('TButton', background='#263b56', foreground=white, padding=7, font=('Segoe UI', 10))
    style.configure('TProgressbar', background=green, troughcolor=panel)

    tk.Label(root, text='РИСЛИ  /  Наведение на спутник', bg=bg, fg=white,
             font=('Segoe UI', 20, 'bold')).pack(anchor='w', padx=22, pady=(14, 4))
    tk.Label(root, text='Два вращающихся клина. Одна неподвижная антенна. Поиск по силе сигнала.',
             bg=bg, fg='#95a9c3', font=('Segoe UI', 11)).pack(anchor='w', padx=22)
    body = tk.Frame(root, bg=bg)
    body.pack(fill='both', expand=True, padx=18, pady=10)
    left = tk.Frame(body, bg=panel)
    left.pack(side='left', fill='both', expand=True, padx=(0, 14))
    right = tk.Frame(body, bg=bg, width=380)
    right.pack(side='right', fill='y')
    scene = tk.Canvas(left, bg=panel, highlightthickness=0)
    scene.pack(fill='both', expand=True)
    scene.bind('<Button-1>', mouse_down)
    scene.bind('<B1-Motion>', mouse_move)
    scene.bind('<Configure>', lambda e: draw())
    signal, angles, progress, best, status = [tk.StringVar() for _ in range(5)]
    for var, size, col in [(signal, 27, green), (angles, 12, white), (best, 11, green)]:
        tk.Label(left, textvariable=var, bg=panel, fg=col, font=('Segoe UI', size)).pack(pady=3)
    tk.Label(left, text='Сигнал за время поиска: синий — текущий, зелёный — лучший',
             bg=panel, fg='#95a9c3', font=('Segoe UI', 10)).pack(pady=(8, 0))
    graph = tk.Canvas(left, height=105, bg=panel, highlightthickness=0)
    graph.pack(fill='x', padx=10)

    controls = tk.Frame(right, bg=bg)
    controls.pack(fill='x')
    entries = []
    fields = [('Q1 — азимут, °', q1), ('Q2 — высота, 0…90°', q2),
              ('Отклонение призмы, 1…30°', otkl), ('Ширина луча, 1…30°', width),
              ('Расстояние дисков, 0.3…1.3', distance), ('Шаг мотора, 0.5…30°', move)]
    for i, (name, value) in enumerate(fields):
        tk.Label(controls, text=name, bg=bg, fg=white, font=('Segoe UI', 10)).grid(row=i, column=0, sticky='w', pady=2)
        entry = tk.Entry(controls, width=10, bg=panel, fg=white, insertbackground=white, relief='flat', font=('Segoe UI', 11))
        entry.insert(0, str(value))
        entry.grid(row=i, column=1, padx=12, pady=2)
        entries.append(entry)
    ttk.Button(right, text='Применить параметры и сбросить поиск', command=apply).pack(fill='x', pady=6)
    buttons = tk.Frame(right, bg=bg)
    buttons.pack(fill='x')
    for name, command in [('Поиск', start), ('Пауза', pause), ('Сброс', reset)]:
        ttk.Button(buttons, text=name, command=command).pack(side='left', expand=True, fill='x', padx=1)
    ttk.Button(right, text='Вернуться к лучшим углам', command=go_best).pack(fill='x', pady=4)
    manual_buttons = tk.Frame(right, bg=bg)
    manual_buttons.pack(fill='x')
    for name, d, s in [('1 −', 1, -1), ('1 +', 1, 1), ('2 −', 2, -1), ('2 +', 2, 1)]:
        ttk.Button(manual_buttons, text=name, width=5, command=lambda d=d, s=s: manual(d, s)).pack(side='left', expand=True, fill='x', padx=1)
    tk.Label(right, text='Измерений за кадр (40 мс). Анимация показывает последнее.',
             bg=bg, fg='#95a9c3', font=('Segoe UI', 9)).pack(pady=(6, 0))
    speed = tk.Scale(right, from_=1, to=2000, orient='horizontal', bg=bg, fg=white,
                     highlightthickness=0, troughcolor=panel)
    speed.set(300)
    speed.pack(fill='x')
    tk.Label(right, text='КАРТА СИГНАЛА  •  ярче = лучше', bg=bg, fg=green, font=('Segoe UI', 11, 'bold')).pack(pady=4)
    heat = tk.PhotoImage(width=360, height=360)
    heat_canvas = tk.Canvas(right, width=240, height=240, bg=bg, highlightthickness=1, highlightbackground='#33445d')
    heat_canvas.pack()
    heat_canvas.create_image(0, 0, anchor='nw', image=heat, tags='map')
    tk.Label(right, text='X: призма 1, 0 → 360°   |   Y: призма 2, 0 ↑ 360°\nТёмные клетки ещё не измерены. Белый кружок — сейчас.',
             bg=bg, fg='#95a9c3', font=('Segoe UI', 9)).pack()
    tk.Label(root, textvariable=progress, bg=bg, fg=white, font=('Segoe UI', 10)).pack()
    bar = ttk.Progressbar(root, maximum=100)
    bar.pack(fill='x', padx=20, pady=4)
    tk.Label(root, textvariable=status, bg=bg, fg=orange, font=('Segoe UI', 10), wraplength=1000).pack(pady=(2, 12))
    reset()
    root.after(40, tick)
    root.mainloop()


if __name__ == '__main__':
    main()
