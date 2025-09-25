def draw_rect(frame, p_xy, prev_p_xy, offset, rect, color=(255, 255, 255)):
    for x, y in rect:
        if prev_p_xy is not None:
            p_xy = (
                prev_p_xy[0] if abs(prev_p_xy[0] - p_xy[0]) > 10 else p_xy[0],
                prev_p_xy[1] if abs(prev_p_xy[1] - p_xy[1]) > 10 else p_xy[1],
            )

        rect_x = x + p_xy[0] + offset[0]
        rect_y = y + p_xy[1] + offset[1]

        if rect_y >= 300 or rect_x >= 350:
            continue

        frame[rect_y, rect_x] = color


def check_rect(frame, p_xy, prev_p_xy, offset, rect) -> float:
    white_count = 0
    for x, y in rect:
        if prev_p_xy is not None:
            p_xy = (
                prev_p_xy[0] if abs(prev_p_xy[0] - p_xy[0]) > 10 else p_xy[0],
                prev_p_xy[1] if abs(prev_p_xy[1] - p_xy[1]) > 10 else p_xy[1],
            )

        rect_x = x + p_xy[0] + offset[0]
        rect_y = y + p_xy[1] + offset[1]

        if rect_y >= 300 or rect_x >= 350:
            continue

        # frame[rect_y, rect_x] = 0

        if frame[rect_y, rect_x] == 255:
            white_count += 1

    return white_count / len(rect) * 100
