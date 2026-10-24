"""Модуль антенны. Здесь только алгоритм и заглушки для отдельного запуска."""


class Ans:
    def __init__(self):
        self.h = float('-inf')
        self.phig1 = 0.0
        self.phig2 = 0.0


class Antenna:
    def __init__(self, modem, gyroscope):
        self.modem = modem
        self.gyroscope = gyroscope
        self.drive = None
        self.mode = 'idle'
        self.ans = Ans()
        self.step = 1.0                 # расстояние между строками поиска, градусы
        self.track_step = 1.0           # пробный шаг сопровождения, градусы
        self.improvement_db = 0.3       # защита от небольшого шума мощности
        self.satellite_angles = (0.0, 0.0)
        self.platform_angles = (0.0, 0.0, 0.0)

    def connect_drive(self, drive):
        self.drive = drive

    def modem_angles(self):
        # Азимут от севера и возвышение НАД ГОРИЗОНТОМ, в градусах.
        return self.modem.angles()

    def gyro_angles(self):
        # Крен, тангаж, курс платформы, в градусах.
        return self.gyroscope.angles()

    def A(self):
        return self.modem.power()

    def move1(self, degrees):
        self.drive.move1(degrees)

    def move2(self, degrees):
        self.drive.move2(degrees)

    def go_to(self, phig1, phig2):
        a, b = self.drive.angles()
        self.move1((phig1-a+180) % 360-180)
        self.move2((phig2-b+180) % 360-180)

    def start(self):
        if self.drive is None:
            raise RuntimeError('Сначала подключи двигатели: connect_drive(drive)')
        if not 0 < self.step <= 360 or not 0 < self.track_step < 180:
            raise ValueError('Проверь step и track_step')
        self.drive.stop()
        self.ans = Ans()
        self.row = 0.0
        self.mode = 'search'
        self.search_state = 'to_start'
        self.go_to(0, 0)
        self.track_state = 'ready'
        self.axis = 1
        self.direction = [1, 1]

    def update(self):
        # Один короткий вызов. Общая прошивка сама выбирает частоту вызовов.
        if self.mode == 'idle':
            return
        self.satellite_angles = self.modem_angles()
        self.platform_angles = self.gyro_angles()
        if self.mode == 'search':
            self.search()
        elif self.mode == 'tracking':
            self.real_time()

    def remember(self):
        h = self.A()
        a, b = self.drive.angles()
        if h > self.ans.h:
            self.ans.h = h
            self.ans.phig1 = a
            self.ans.phig2 = b

    def search(self):
        # Как раньше: перебираем первую призму и полный оборот второй.
        # Теперь во время оборота измеряем сигнал, не задерживая прошивку.
        if self.search_state == 'scan':
            self.remember()
            if self.drive.busy():
                return
            self.row += self.step
            if self.row >= 360:
                self.go_to(self.ans.phig1, self.ans.phig2)
                self.search_state = 'to_best'
            else:
                self.move1(self.step)
                self.search_state = 'to_row'
            return

        if self.drive.busy():
            return
        if self.search_state == 'to_best':
            self.mode = 'tracking'
            return

        self.remember()
        self.move2(360)
        self.search_state = 'scan'

    def real_time(self):
        import math

        # Параметры НАШИХ призм и привода. В прошивке нужны их реальные значения.
        n = math.sqrt(2.53)
        wedge1, wedge2 = 20.0, 20.0
        move_seconds = 1.0
        probe_step = 0.5
        max_trim = 4.0

        def dot(a, b):
            return sum(x*y for x, y in zip(a, b))

        def unit(v):
            length = math.sqrt(dot(v, v))
            return tuple(x/length for x in v)

        def ray(angles):
            # Закон Снеллиуса на четырёх границах. Углы НЕ считаем малыми.
            d = (0.0, 0.0, 1.0)
            for phi, wedge in zip(angles, (wedge1, wedge2)):
                p, w = math.radians(phi), math.radians(wedge)
                normal = (math.sin(w)*math.cos(p), math.sin(w)*math.sin(p), math.cos(w))
                for normal, n1, n2 in (((0, 0, -1), 1, n), (normal, n, 1)):
                    if dot(d, normal) > 0:
                        normal = tuple(-x for x in normal)
                    cosine = -dot(d, normal)
                    eta = n1/n2
                    k = 1-eta*eta*(1-cosine*cosine)
                    if k < 0:
                        return None
                    d = unit(tuple(eta*x+(eta*cosine-math.sqrt(k))*y
                                   for x, y in zip(d, normal)))
            return d

        def solve(target, angles):
            # Локальная линейная поправка: (JᵀJ + λI) Δφ = Jᵀ(target-ray).
            # Несколько коротких итераций нужны при заметном смещении цели.
            angles = list(angles)
            for _ in range(10):
                d = ray(angles)
                if d is None:
                    break
                error = tuple(x-y for x, y in zip(target, d))
                columns = []
                for axis in (0, 1):
                    shifted = angles.copy()
                    shifted[axis] += 0.05
                    other = ray(shifted)
                    if other is None:
                        return angles
                    columns.append(tuple((x-y)/0.05 for x, y in zip(other, d)))
                j1, j2 = columns
                aa, bb = dot(j1, j1)+1e-7, dot(j2, j2)+1e-7
                ab = dot(j1, j2)
                e1, e2 = dot(j1, error), dot(j2, error)
                determinant = aa*bb-ab*ab
                delta = ((bb*e1-ab*e2)/determinant, (aa*e2-ab*e1)/determinant)
                for axis in (0, 1):
                    angles[axis] += max(-12, min(12, delta[axis]))
                if max(abs(x) for x in delta) < 0.01:
                    break
            return angles

        # ENU: восток, север, вверх. Корпус: вперёд, влево, вверх.
        az, el = map(math.radians, self.satellite_angles)
        roll, pitch, yaw = map(math.radians, self.platform_angles)
        x, y, z = math.cos(el)*math.sin(az), math.cos(el)*math.cos(az), math.sin(el)
        heading = math.pi/2-yaw
        x, y = math.cos(heading)*x+math.sin(heading)*y, -math.sin(heading)*x+math.cos(heading)*y
        x, z = math.cos(pitch)*x+math.sin(pitch)*z, -math.sin(pitch)*x+math.cos(pitch)*z
        y, z = math.cos(roll)*y+math.sin(roll)*z, -math.sin(roll)*y+math.cos(roll)*z
        target = (x, y, z)
        now = self.drive.clock()

        if not hasattr(self, '_tracking') or self.track_state == 'ready':
            self._tracking = dict(time=now, target=target, velocity=(0, 0, 0),
                                  trim=[0.0, 0.0], axis=0, sign=1, stage='baseline')
            self.track_state = 'following'
        state = self._tracking

        # Фильтр скорости направления, без разрывов азимута при 359° → 0°.
        dt = now-state['time']
        if dt >= 0.1:
            measured = tuple((x-y)/dt for x, y in zip(target, state['target']))
            weight = 1-math.exp(-dt/0.5)
            state['velocity'] = tuple((1-weight)*v+weight*m for v, m in zip(state['velocity'], measured))
            state['time'], state['target'] = now, target
        if self.drive.busy():
            return

        angles = self.drive.angles()
        power = self.A()
        axis = state['axis']
        if state['stage'] == 'compare':
            if power > state['power']+self.improvement_db:
                # Улучшение: продолжаем в том же направлении.
                state['stage'] = 'baseline'
            else:
                # Откатываем пробу, но не компенсацию движения спутника.
                state['trim'][axis] = state['before_trim']
                state['sign'] *= -1
                state['axis'] = 1-axis
                state['stage'] = 'settle'
        elif state['stage'] == 'baseline':
            state['power'] = power
            state['before_trim'] = state['trim'][axis]
            state['trim'][axis] = max(-max_trim, min(max_trim, state['trim'][axis]+state['sign']*probe_step))
            state['stage'] = 'compare'
        else:
            state['stage'] = 'baseline'

        # Целимся туда, где направление будет через время движения мотора.
        predicted = unit(tuple(x+move_seconds*v for x, v in zip(target, state['velocity'])))
        desired = solve(predicted, angles)
        self.go_to(*(a+trim for a, trim in zip(desired, state['trim'])))


    def stop(self):
        if self.drive is not None:
            self.drive.stop()
        self.mode = 'idle'


class Modem:
    """Заглушка для отдельного запуска. Спутник неподвижен над горизонтом."""
    def angles(self):
        return 55.0, 70.0

    def power(self):
        return -80.0


class Gyroscope:
    """Заглушка: горизонтальная платформа, её нос смотрит на север."""
    def angles(self):
        return 0.0, 0.0, 0.0


if __name__ == '__main__':
    antenna = Antenna(Modem(), Gyroscope())
    print('Модем: азимут, возвышение =', antenna.modem_angles())
    print('Гироскоп: крен, тангаж, курс =', antenna.gyro_angles())
    print('Мощность =', antenna.A(), 'dBm')
    print('Для управления подключи drive и вызывай start(), затем update().')
