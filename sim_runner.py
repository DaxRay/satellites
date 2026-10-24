import builtins
import ast
import hashlib
import math
import random
import sys
import time
import types
from pathlib import Path

import sim_settings as s
import sim_physics as p


class TestEnd(BaseException):
    pass


class SimTime:
    # Одни часы для вращения, A(), time.time(), monotonic() и sleep().
    def monotonic(self):
        return now

    def perf_counter(self):
        return now

    def time(self):
        return epoch + now

    def sleep(self, delay):
        if delay < 0:
            raise ValueError('sleep length must be non-negative')
        advance(delay)

    def __getattr__(self, name):
        return getattr(time, name)


class SimTimer:
    # Timer выполняется по часам стенда. Поток Python не блокируется.
    def __init__(self, interval, function, args=None, kwargs=None):
        self.interval = interval
        self.function = function
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.daemon = False
        self.cancelled = False
        self.end = None

    def start(self):
        self.end = now + self.interval
        timers.append(self)

    def cancel(self):
        self.cancelled = True

    def is_alive(self):
        return self.end is not None and not self.cancelled and now < self.end

    def join(self, timeout=None):
        if self.is_alive():
            advance(min(self.end-now, timeout) if timeout is not None else self.end-now)


def sat_now():
    t = 0 if phase == 'search' else seconds
    return p.satellite(s.start_orbit_seconds + t)


def snapshot():
    sat = sat_now()
    return {'phase': phase, 'seconds': seconds, 'phig1': phig1, 'phig2': phig2,
            'sat': sat, 'power': p.power(phig1, phig2, sat), 'measured': last_h,
            'error': p.error(phig1, phig2, sat), 'measurements': measurements,
            'moves': moves, 'reachable': p.reachable(sat),
            'moving1': bool(motors[0]), 'moving2': bool(motors[1]),
            'motor_mode': motor_mode}


def send(kind, value):
    if connection is not None:
        connection.send((kind, value))


def pace(force=False):
    global last_emit, pace_sim, pace_wall
    speed = acceleration.value if acceleration is not None else 0
    if speed > 0 and now-pace_sim >= speed*0.04:
        delay = (now-pace_sim)/speed - (time.monotonic()-pace_wall)
        if delay > 0:
            time.sleep(min(delay, 0.1))
        pace_sim, pace_wall = now, time.monotonic()
    if force or time.monotonic()-last_emit > 0.06:
        send('frame', snapshot())
        last_emit = time.monotonic()


def update_motor(i):
    global phig1, phig2
    motor = motors[i]
    if motor is None:
        return
    start, angle, delta, duration = motor
    elapsed = min(duration, max(0, now-start))
    value = (angle + delta*elapsed/duration) % 360
    if i == 0:
        phig1 = value
    else:
        phig2 = value
    # В пошаговом main оба счётчика прибавляются самим пользовательским кодом.
    # В непрерывном режиме второй угол main читает прямо во время оборота.
    if s.update_main_angles or (motor_mode == 'continuous' and i == 1):
        user.__dict__['phig1' if i == 0 else 'phig2'] = value
    if elapsed >= duration-1e-10:
        value = round(angle+delta, 10) % 360
        if i == 0:
            phig1 = value
        else:
            phig2 = value
        if s.update_main_angles or (motor_mode == 'continuous' and i == 1):
            user.__dict__['phig1' if i == 0 else 'phig2'] = value
        motors[i] = None
        user.__dict__['is_move1' if i == 0 else 'is_move2'] = False


def update_at(t):
    global now, seconds
    now = t
    seconds = max(0, now-phase_origin)
    update_motor(0)
    update_motor(1)
    # Колбэки пользовательских Timer, если они используются вне move1/move2.
    for timer in list(timers):
        if timer.cancelled:
            timers.remove(timer)
        elif timer.end <= now + 1e-10:
            timers.remove(timer)
            timer.cancelled = True
            timer.function(*timer.args, **timer.kwargs)


def record(dt):
    global visible_time, reachable_time, linked_time, visible_linked_time
    global error_squared, first_lock, longest_loss, loss_time
    sat = sat_now()
    h = p.power(phig1, phig2, sat)
    if sat['visible'] and h >= s.link_threshold_dbm and first_lock is None:
        first_lock = seconds
    if phase != 'flight':
        return
    if sat['visible']:
        visible_time += dt
        if h >= s.link_threshold_dbm:
            visible_linked_time += dt
    if p.reachable(sat):
        reachable_time += dt
        error_squared += p.error(phig1, phig2, sat)**2 * dt
        if h >= s.link_threshold_dbm:
            linked_time += dt
            loss_time = 0
        else:
            loss_time += dt
            longest_loss = max(longest_loss, loss_time)
    else:
        loss_time = 0


def advance(dt):
    global next_quality
    if not isinstance(dt, (int, float)) or not math.isfinite(dt) or dt < 0:
        raise ValueError('Время должно быть конечным неотрицательным числом')
    limit = s.search_limit_seconds if phase == 'search' else s.flight_seconds
    end = min(now+dt, phase_origin+limit)
    while next_quality <= end+1e-10:
        update_at(min(next_quality, end))
        record(s.sample_seconds)
        next_quality += s.sample_seconds
        pace()
    update_at(end)
    pace()
    if seconds >= limit-1e-9:
        raise TestEnd()


def move_disk(i, angle):
    global moves, travelled
    update_motor(i)
    if angle is None:
        angle = s.step_deg if motor_mode == 'step' or i == 0 else s.default_turn2_deg
    if not isinstance(angle, (int, float)) or not math.isfinite(angle):
        raise ValueError('Угол движения должен быть конечным числом градусов')
    start = phig1 if i == 0 else phig2
    duration = s.step_seconds*abs(angle)/s.step_deg if motor_mode == 'step' else s.turn_seconds
    motors[i] = (now, start, angle, duration) if angle else None
    user.__dict__['is_move1' if i == 0 else 'is_move2'] = bool(angle)
    user.__dict__['start_time1' if i == 0 else 'start_time2'] = now
    user.__dict__['start_angle1' if i == 0 else 'start_angle2'] = start
    user.__dict__['speed1' if i == 0 else 'speed2'] = angle / duration if duration else 0
    # Твой update_angles() использует duration и эти начальные условия.
    user.duration = duration
    moves += 1
    travelled += abs(angle)
    if motor_mode == 'step' and angle:
        # Старый main: движение завершено, затем он сам делает phig += move.
        advance(duration)
    # В continuous сразу возвращаем управление, вращение идёт дальше.


def move1(angles=None):
    move_disk(0, angles)


def move2(angles=None):
    move_disk(1, angles)


def stop1():
    update_motor(0)
    motors[0] = None
    user.is_move1 = False


def stop2():
    update_motor(1)
    motors[1] = None
    user.is_move2 = False


def A():
    global measurements, last_h
    advance(s.measure_seconds)
    measurements += 1
    if s.signal_from_main:
        if original_A is None:
            raise RuntimeError('В main.py нет исходной A(). Отключи signal_from_main, чтобы использовать прибор эмулятора.')
        last_h = original_A()
    else:
        last_h = max(s.floor_dbm, p.power(phig1, phig2, sat_now()) + rng.gauss(0, s.noise_db))
    return last_h


def answer(value):
    if hasattr(value, 'phig1') and hasattr(value, 'phig2'):
        value = (value.h, value.phig1, value.phig2)
    elif isinstance(value, dict):
        value = (value.get('h'), value.get('phig1'), value.get('phig2'))
    if isinstance(value, (tuple, list)) and len(value) == 3:
        if all(isinstance(x, (int, float)) and math.isfinite(x) for x in value):
            return tuple(float(x) for x in value)
    return None


def user_print(*args, **kwargs):
    global printed_answer, last_log
    found = answer(args)
    if found is None and len(args) >= 3:
        found = answer(args[-3:])
    if found is not None and phase == 'search':
        printed_answer = found
    if connection is None:
        builtins.print(*args, **kwargs)
    elif time.monotonic()-last_log > 0.1:
        send('log', ' '.join(str(x) for x in args)[:2000])
        last_log = time.monotonic()


def import_for_main(name, globals=None, locals=None, fromlist=(), level=0):
    module = builtins.__import__(name, globals, locals, fromlist, level)
    if level == 0 and name == 'time':
        return sim_time
    if level == 0 and name == 'threading':
        return sim_threading
    return module


def install_devices():
    global original_A
    # Файл выполняется целиком, определения из main могут появляться по ходу.
    # Подмена действует только в памяти процесса эмулятора.
    for name, function in [('A', A), ('move1', move1), ('move2', move2), ('stop1', stop1), ('stop2', stop2)]:
        current = user.__dict__.get(name)
        if current is None:
            user.__dict__[name] = function
        elif callable(current) and current is not function:
            if name == 'A':
                original_A = current
            user.__dict__[name] = function


def choose_motor_mode(source):
    if s.motor_mode != 'auto':
        return s.motor_mode
    tree = ast.parse(source)
    # Цикл ожидания флага движения означает непрерывный привод.
    for node in ast.walk(tree):
        if isinstance(node, ast.While):
            if any(isinstance(n, ast.Name) and n.id in ('is_move1', 'is_move2')
                   for n in ast.walk(node.test)):
                return 'continuous'
    # Timer/sleep внутри двигателей также означают реализацию непрерывного привода.
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in ('move1', 'move2'):
            if node.args.args or node.args.kwonlyargs or node.args.vararg or node.args.kwarg:
                return 'continuous'
            for part in ast.walk(node):
                if isinstance(part, ast.Name) and part.id == 'Timer':
                    return 'continuous'
    # Пустые move1/move2 и ручной подсчёт углов: исходный пошаговый main.
    return 'step'


def grid_maximum(sat):
    best = (-float('inf'), 0, 0)
    n = math.ceil(360/s.step_deg)
    if n > 720:
        return None
    for i in range(n):
        for j in range(n):
            a, b = i*s.step_deg, j*s.step_deg
            h = p.power(a, b, sat)
            if h > best[0]:
                best = (h, a, b)
    return best


def search_report(result, ended):
    fixed_sat = sat_now()
    optimum = grid_maximum(fixed_sat)
    report = {'seconds': seconds, 'first_lock': first_lock,
              'measurements': measurements, 'moves': moves, 'ended': ended,
              'answer': result, 'optimum': optimum, 'actual_angles': [phig1, phig2],
              'actual_power': p.power(phig1, phig2, fixed_sat), 'angle_mismatches': 0,
              'travelled_deg': travelled, 'motor_mode': motor_mode}
    if result is not None:
        h, a, b = result
        report['answer_power'] = p.power(a, b, fixed_sat)
        report['answer_error'] = p.error(a, b, fixed_sat)
        report['gap_db'] = optimum[0]-report['answer_power'] if optimum else None
        report['on_step_grid'] = all(abs(x/s.step_deg-round(x/s.step_deg)) < 1e-5 for x in (a, b))
    return report


def begin(name):
    global phase, seconds, phase_origin, next_quality, first_lock
    global measurements, moves, travelled
    phase = name
    phase_origin = now
    seconds = 0
    next_quality = now+s.sample_seconds
    first_lock = None
    measurements = moves = 0
    travelled = 0
    pace(True)


def finish_search(result, ended):
    global search, printed_answer
    if search is not None:
        return
    search = search_report(result, ended)
    send('search_result', search)
    printed_answer = None
    begin('flight')


def trace_main(frame, event, arg):
    global user_main_frame, controller_seen
    if frame.f_code.co_filename != main_filename:
        return None
    install_devices()
    if event == 'call':
        name = frame.f_code.co_name
        if name == 'main' and search is None:
            user_main_frame = frame
        elif name in ('real_time', 'track') and phase == 'flight':
            controller_seen = True
    if event == 'line':
        # Малая фиксированная стоимость строки позволяет двигаться и в busy-wait.
        # Иначе while is_move2: pass никогда не отдал бы время механизму.
        advance(s.python_line_seconds)
    if event == 'return' and frame is user_main_frame and sys.exc_info()[0] is None:
        result = answer(arg) or printed_answer or answer(frame.f_locals.get('ans'))
        finish_search(result, 'returned')
    return trace_main


def run(path, pipe=None, speed=None, settings=None):
    global connection, acceleration, user, phase, seconds, now, phig1, phig2
    global measurements, moves, travelled, last_h, rng, epoch, motors, timers
    global last_emit, last_log, pace_sim, pace_wall, printed_answer, original_A
    global visible_time, reachable_time, linked_time, visible_linked_time
    global error_squared, longest_loss, loss_time, search, user_main_frame
    global sim_time, sim_threading, main_filename, controller_seen
    global motor_mode
    connection, acceleration = pipe, speed
    previous_main = sys.modules.get('__main__')
    previous_argv, previous_path = sys.argv, list(sys.path)
    previous_trace = sys.gettrace()
    try:
        if settings:
            for name, value in settings.items():
                if hasattr(s, name) and not name.startswith('_'):
                    setattr(s, name, value)
        p.validate()
        rng = random.Random(s.seed)
        now = seconds = phig1 = phig2 = 0.0
        epoch = time.time()
        motors, timers = [None, None], []
        measurements = moves = travelled = 0
        last_h = s.floor_dbm
        last_emit = last_log = pace_sim = 0
        pace_wall = time.monotonic()
        printed_answer = original_A = search = user_main_frame = None
        A.__dict__.clear()
        controller_seen = False
        visible_time = reachable_time = linked_time = visible_linked_time = 0.0
        error_squared = longest_loss = loss_time = 0.0

        path = Path(path).resolve()
        source = path.read_bytes()
        motor_mode = choose_motor_mode(source)
        main_filename = str(path)
        user = types.ModuleType('__main__')
        user.__file__, user.__package__, user.__spec__ = main_filename, None, None
        user.__dict__.update(phig1=0, phig2=0, is_move1=False, is_move2=False,
                             A=A, move1=move1, move2=move2, stop1=stop1, stop2=stop2)
        sim_time = SimTime()
        import threading
        sim_threading = types.ModuleType('threading')
        sim_threading.__dict__.update(vars(threading))
        sim_threading.Timer = SimTimer
        custom_builtins = dict(vars(builtins))
        custom_builtins['__import__'] = import_for_main
        custom_builtins['print'] = user_print
        user.__builtins__ = custom_builtins
        sys.modules['__main__'] = user
        sys.argv = [main_filename]
        sys.path.insert(0, str(path.parent))
        begin('search')
        ended = 'script_returned'
        error_text = None
        try:
            sys.settrace(trace_main)
            # Включая if __name__ == '__main__': и все циклы, написанные тобой.
            exec(compile(source, main_filename, 'exec'), user.__dict__)
        except TestEnd:
            ended = 'time_limit'
        except SystemExit as exc:
            if exc.code not in (None, 0):
                import traceback
                error_text = traceback.format_exc()
        except BaseException:
            import traceback
            error_text = traceback.format_exc()
        finally:
            sys.settrace(previous_trace)

        if search is None:
            finish_search(printed_answer, 'error' if error_text else ended)
        if error_text:
            send('error', error_text)
        # Если файл закончился, продолжаем наблюдать полёт без запуска новых функций.
        # Диски завершают только команды, которые действительно выдал пользователь.
        returned_at = seconds if ended == 'script_returned' or error_text else None
        try:
            advance(max(0, s.flight_seconds-seconds))
        except TestEnd:
            pass
        pace(True)
        flight = {'seconds': seconds, 'function': 'код из блока __main__',
                  'returned_at': returned_at, 'controller_seen': controller_seen,
                  'visible_seconds': visible_time, 'reachable_seconds': reachable_time,
                  'linked_seconds': linked_time,
                  'linked_percent': 100*linked_time/reachable_time if reachable_time else None,
                  'visible_linked_percent': 100*visible_linked_time/visible_time if visible_time else None,
                  'rms_error': math.sqrt(error_squared/reachable_time) if reachable_time else None,
                  'longest_loss': longest_loss, 'measurements': measurements, 'moves': moves,
                  'angle_mismatches': 0, 'travelled_deg': travelled}
        report = {'search': search, 'flight': flight, 'error': error_text,
                  'motor_mode': motor_mode,
                  'signal_from_main': s.signal_from_main,
                  'main_sha256': hashlib.sha256(source).hexdigest(),
                  'settings': {name: value for name, value in vars(s).items()
                               if not name.startswith('_') and isinstance(value, (int, float, bool, str))}}
        send('done', report)
        return report
    except BaseException:
        import traceback
        send('error', traceback.format_exc())
        if connection is None:
            raise
    finally:
        sys.settrace(previous_trace)
        if previous_main is not None:
            sys.modules['__main__'] = previous_main
        sys.argv, sys.path[:] = previous_argv, previous_path
        if connection is not None:
            connection.close()
