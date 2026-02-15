# resona_desktop_pet/physics/engine.py

class PhysicsEngine:
    def __init__(
        self,
        gravity=30.0,
        accel_x=0.0,
        accel_y=0.0,
        friction=0.98,
        elasticity=0.6,
        max_speed=2000.0,
        gravity_enabled=True,
        accel_enabled=False,
        invert_forces=False,
        friction_enabled=True,
        bounce_enabled=True
    ):
        self.gravity = gravity
        self.accel_x = accel_x
        self.accel_y = accel_y
        self.friction = friction
        self.elasticity = elasticity
        self.max_speed = max_speed
        self.gravity_enabled = gravity_enabled
        self.accel_enabled = accel_enabled
        self.invert_forces = invert_forces
        self.friction_enabled = friction_enabled
        self.bounce_enabled = bounce_enabled

        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0

        self.is_active = True
        self.last_ax = 0.0
        self.last_ay = 0.0
        self.last_accel = 0.0
        self.bounce_count = 0
        self.window_collision_count = 0

    def set_position(self, x, y):
        self.x = x
        self.y = y

    def set_velocity(self, vx, vy):
        self.vx = vx
        self.vy = vy

    def reset_counters(self):
        self.bounce_count = 0
        self.window_collision_count = 0

    def step(self, dt=1.0):
        if not self.is_active:
            return
        if dt <= 0:
            return

        ax = 0.0
        ay = 0.0
        if self.gravity_enabled:
            ay += self.gravity
        if self.accel_enabled:
            ax += self.accel_x
            ay += self.accel_y
        if self.invert_forces:
            ax = -ax
            ay = -ay

        self.last_ax = ax
        self.last_ay = ay
        self.last_accel = (ax * ax + ay * ay) ** 0.5

        self.vx += ax * dt
        self.vy += ay * dt

        if self.max_speed > 0:
            speed_sq = self.vx * self.vx + self.vy * self.vy
            max_sq = self.max_speed * self.max_speed
            if speed_sq > max_sq:
                ratio = (max_sq / speed_sq) ** 0.5
                self.vx *= ratio
                self.vy *= ratio

        self.x += self.vx * dt
        self.y += self.vy * dt

        if self.friction_enabled:
            if self.friction < 0:
                self.friction = 0.0
            if self.friction > 1:
                self.friction = 1.0
            damp = self.friction ** dt
            self.vx *= damp
            self.vy *= damp

    def resolve_bounds(self, bounds_rect, pet_width, pet_height):
        left = bounds_rect.left()
        top = bounds_rect.top()
        right = bounds_rect.right() + 1
        bottom = bounds_rect.bottom() + 1

        if self.y + pet_height > bottom:
            self.y = bottom - pet_height
            if self.bounce_enabled:
                self.vy = -abs(self.vy) * self.elasticity
                self.bounce_count += 1
            else:
                self.vy = 0.0
        if self.y < top:
            self.y = top
            if self.bounce_enabled:
                self.vy = abs(self.vy) * self.elasticity
                self.bounce_count += 1
            else:
                self.vy = 0.0
        if self.x < left:
            self.x = left
            if self.bounce_enabled:
                self.vx = abs(self.vx) * self.elasticity
                self.bounce_count += 1
            else:
                self.vx = 0.0
        if self.x + pet_width > right:
            self.x = right - pet_width
            if self.bounce_enabled:
                self.vx = -abs(self.vx) * self.elasticity
                self.bounce_count += 1
            else:
                self.vx = 0.0

    def resolve_rect_collisions(self, rects, pet_width, pet_height):
        for rect in rects:
            left = rect.left()
            top = rect.top()
            right = rect.right() + 1
            bottom = rect.bottom() + 1

            if self.x >= right or self.x + pet_width <= left:
                continue
            if self.y >= bottom or self.y + pet_height <= top:
                continue

            overlap_left = (self.x + pet_width) - left
            overlap_right = right - self.x
            overlap_top = (self.y + pet_height) - top
            overlap_bottom = bottom - self.y

            min_overlap = min(overlap_left, overlap_right, overlap_top, overlap_bottom)
            if min_overlap == overlap_left:
                self.x = left - pet_width
                if self.bounce_enabled:
                    self.vx = -abs(self.vx) * self.elasticity
                    self.bounce_count += 1
                else:
                    self.vx = 0.0
            elif min_overlap == overlap_right:
                self.x = right
                if self.bounce_enabled:
                    self.vx = abs(self.vx) * self.elasticity
                    self.bounce_count += 1
                else:
                    self.vx = 0.0
            elif min_overlap == overlap_top:
                self.y = top - pet_height
                if self.bounce_enabled:
                    self.vy = -abs(self.vy) * self.elasticity
                    self.bounce_count += 1
                else:
                    self.vy = 0.0
            else:
                self.y = bottom
                if self.bounce_enabled:
                    self.vy = abs(self.vy) * self.elasticity
                    self.bounce_count += 1
                else:
                    self.vy = 0.0
            self.window_collision_count += 1
