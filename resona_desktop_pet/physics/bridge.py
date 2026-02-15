# resona_desktop_pet/physics/bridge.py
import time
import sys
import ctypes
from PySide6.QtCore import QObject, QTimer, QPoint, QRect, Qt
from .engine import PhysicsEngine
from .env_scanner import EnvironmentScanner

class PhysicsBridge(QObject):
    def __init__(self, target_window, config):
        super().__init__(target_window)
        self.target = target_window
        self.config = config
        self.enabled = True

        self.engine = PhysicsEngine(
            gravity=self.config.physics_gravity,
            accel_x=self.config.physics_accel_x,
            accel_y=self.config.physics_accel_y,
            friction=self.config.physics_friction,
            elasticity=self.config.physics_elasticity,
            max_speed=self.config.physics_max_speed,
            gravity_enabled=self.config.physics_gravity_enabled,
            accel_enabled=self.config.physics_accel_enabled,
            invert_forces=self.config.physics_invert_forces,
            friction_enabled=self.config.physics_friction_enabled,
            bounce_enabled=self.config.physics_bounce_enabled
        )

        sprite_rect = self._get_sprite_rect()
        self.engine.set_position(sprite_rect.left(), sprite_rect.top())

        self.last_pos = QPoint(sprite_rect.left(), sprite_rect.top())
        self.last_time = time.time()
        self.last_dragging = False
        self.was_moving = False
        self.fall_distance = 0.0
        self.last_window_pos = self.target.pos()
        self.still_ticks = 0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self._start_timer()

    def _start_timer(self):
        refresh_rate = self.config.physics_refresh_rate
        if refresh_rate <= 0:
            refresh_rate = EnvironmentScanner.get_screen_refresh_rate(self.target)
        refresh_rate = max(1.0, float(refresh_rate))
        interval = int(1000.0 / refresh_rate)
        interval = max(1, interval)
        self.timer.start(interval)

    def _ensure_topmost(self):
        if not self.config.always_on_top or sys.platform != "win32":
            return
        try:
            if hasattr(self.target, "windowFlags"):
                if not (self.target.windowFlags() & Qt.WindowType.WindowStaysOnTopHint):
                    self.target.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
                    self.target.show()
                    self.target.raise_()
            hwnd = self.target.winId()
            if not isinstance(hwnd, int):
                hwnd = int(hwnd)
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0040)
        except:
            pass

    def _get_sprite_rect(self):
        if hasattr(self.target, "get_sprite_collision_rect"):
            rect = self.target.get_sprite_collision_rect()
            if rect and not rect.isEmpty():
                return rect
        geo = self.target.frameGeometry()
        return geo

    def _reset_motion_stats(self):
        self.engine.reset_counters()
        self.fall_distance = 0.0
        self.was_moving = False
        self._sync_stats(reset=True)

    def _sync_stats(self, reset=False):
        stats = getattr(self.target, "stats", None)
        if stats is None:
            return
        stats["physics_acceleration"] = 0.0 if reset else getattr(self.engine, "last_accel", 0.0)
        stats["physics_bounce_count"] = getattr(self.engine, "bounce_count", 0)
        stats["physics_fall_distance"] = self.fall_distance
        stats["physics_window_collision_count"] = getattr(self.engine, "window_collision_count", 0)

    def _on_tick(self):
        if not self.enabled:
            return
        if not hasattr(self, "_tick_count"): self._tick_count = 0
        self._tick_count += 1
        if self._tick_count % 300 == 0:
            pass # print(f"[Physics] Tick {self._tick_count}: pos=({self.engine.x:.1f}, {self.engine.y:.1f}), v=({self.engine.vx:.1f}, {self.engine.vy:.1f})")

        sprite_rect = self._get_sprite_rect()
        window_pos = self.target.frameGeometry().topLeft()
        sprite_offset = sprite_rect.topLeft() - window_pos
        current_pos = QPoint(sprite_rect.left(), sprite_rect.top())
        current_time = time.time()
        dt = current_time - self.last_time
        if dt <= 0:
            return
        
        dt = min(dt, 0.05)
        
        actual_window_pos = self.target.frameGeometry().topLeft()
        if not self.last_dragging and actual_window_pos != self.last_window_pos:
            if (actual_window_pos - self.last_window_pos).manhattanLength() > 1:
                self.engine.set_position(sprite_rect.left(), sprite_rect.top())
                self.last_pos = QPoint(sprite_rect.left(), sprite_rect.top())
        
        self.last_window_pos = actual_window_pos
        is_dragging = getattr(self.target, "dragging", False)
        
        if is_dragging:
            raw_vx = (current_pos.x() - self.last_pos.x()) / dt
            raw_vy = (current_pos.y() - self.last_pos.y()) / dt

            alpha = 0.4
            new_vx = self.engine.vx * (1 - alpha) + raw_vx * alpha
            new_vy = self.engine.vy * (1 - alpha) + raw_vy * alpha
            
            vx = new_vx * self.config.physics_drag_velocity_multiplier
            vy = new_vy * self.config.physics_drag_velocity_multiplier
            
            self.engine.set_velocity(vx, vy)
            self.engine.set_position(current_pos.x(), current_pos.y())
            
            self.last_pos = current_pos
            self.last_time = current_time
            self.last_window_pos = actual_window_pos
            self.last_dragging = True
            self._sync_stats(reset=True)
            return


        if self.last_dragging:
            self.engine.set_position(current_pos.x(), current_pos.y())
            self.last_pos = current_pos
            self.last_window_pos = actual_window_pos
            # print(f"[Physics] Drag released, final v=({self.engine.vx:.1f}, {self.engine.vy:.1f})")
            
        self.last_dragging = False

        self.engine.step(dt)

        sleep_speed = max(0.0, float(self.config.physics_sleep_speed_threshold))
        sleep_frames = max(1, int(self.config.physics_sleep_still_frames))
        moving = abs(self.engine.vx) > sleep_speed or abs(self.engine.vy) > sleep_speed
        if self.was_moving and not moving:
            self._reset_motion_stats()
        self.was_moving = moving

        screen_rect = EnvironmentScanner.get_screen_geometry(self.target)
        padding = self.config.physics_screen_padding
        if padding:
            screen_rect = screen_rect.adjusted(padding, padding, -padding, -padding)

        pet_w = sprite_rect.width()
        pet_h = sprite_rect.height()
        window_geo = self.target.frameGeometry()
        window_w = window_geo.width()
        window_h = window_geo.height()
        dialog_rect = None
        if hasattr(self.target, "io"):
            dialog_rect = self.target.io.geometry()

        if dialog_rect and not dialog_rect.isEmpty():
            dialog_x = dialog_rect.x()
            dialog_w = dialog_rect.width()
            bounds_left = screen_rect.left() + sprite_offset.x() - dialog_x
            bounds_right_limit = screen_rect.right() - dialog_w + 1 - dialog_x + sprite_offset.x() + pet_w
        else:
            bounds_left = screen_rect.left() + sprite_offset.x()
            bounds_right_limit = screen_rect.right() + 1 + sprite_offset.x()

        bounds_top = screen_rect.top()
        bounds_bottom_limit = screen_rect.bottom() + 1
        bounds_w = max(1, bounds_right_limit - bounds_left)
        bounds_h = max(1, bounds_bottom_limit - bounds_top)
        bounds_rect = QRect(bounds_left, bounds_top, bounds_w, bounds_h)
        self.engine.resolve_bounds(bounds_rect, pet_w, pet_h)

        if self.config.physics_collide_windows:
            ignore_hwnds = [self.target.winId()]
            rects = EnvironmentScanner.get_window_rects(
                ignore_hwnds=ignore_hwnds,
                ignore_maximized=self.config.physics_ignore_maximized_windows,
                ignore_fullscreen=self.config.physics_ignore_fullscreen_windows,
                ignore_borderless_fullscreen=self.config.physics_ignore_borderless_fullscreen
            )
            if rects:
                self.engine.resolve_rect_collisions(rects, pet_w, pet_h)

        new_sprite_x = int(self.engine.x)
        new_sprite_y = int(self.engine.y)
        
        target_x = new_sprite_x - sprite_offset.x()
        target_y = new_sprite_y - sprite_offset.y()
        new_window_pos = QPoint(target_x, target_y)
        move_delta = new_window_pos - window_pos
        if move_delta.manhattanLength() == 0:
            self.still_ticks += 1
        else:
            self.still_ticks = 0

        if self.still_ticks >= sleep_frames and not is_dragging and not self.last_dragging:
            if abs(self.engine.vx) < sleep_speed and abs(self.engine.vy) < sleep_speed:
                self.engine.set_velocity(0.0, 0.0)
                self.engine.set_position(new_sprite_x, new_sprite_y)
                self.was_moving = False
                self._reset_motion_stats()

        dy = new_sprite_y - self.last_pos.y()
        if dy > 0:
            self.fall_distance += dy

        if target_x != window_pos.x() or target_y != window_pos.y():
            moved = False
            if self.config.always_on_top and sys.platform == "win32":
                hwnd = int(self.target.winId())
                SWP_NOSIZE = 0x0001
                SWP_NOACTIVATE = 0x0010
                SWP_SHOWWINDOW = 0x0040
                res = ctypes.windll.user32.SetWindowPos(hwnd, -1, target_x, target_y, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
                moved = bool(res)
            if not moved:
                self.target.move(new_window_pos)
            
            self.last_window_pos = new_window_pos
            
            if self.config.always_on_top and hasattr(self.target, "_reinforce_topmost"):
                self.target._reinforce_topmost()

        if self.config.always_on_top and hasattr(self.target, "_reinforce_topmost"):
            self.target._reinforce_topmost()
            if hasattr(self.target, "topmost_timer") and not self.target.topmost_timer.isActive():
                self.target.topmost_timer.start()

        self.last_pos = QPoint(new_sprite_x, new_sprite_y)
        self.last_time = current_time
        self._sync_stats()
        self._ensure_topmost()

    def set_enabled(self, enabled):
        self.enabled = enabled
        if enabled:
            self._reset_motion_stats()
            if not self.timer.isActive():
                self._start_timer()
        else:
            self.timer.stop()
            self._reset_motion_stats()
