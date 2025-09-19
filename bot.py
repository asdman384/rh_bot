import time
import winsound

import cv2

from boss import BossBhalor, BossDain, BossElvira, BossKhanel, BossMine
from bot_utils.screenshoter import save_image
from controller import Controller
from detect_boss_room import wait_for_boss_popup
from detect_location import find_tpl, wait_for, wait_loading
from devices.device import Device
from explorer import Explorer
from frames import extract_game
from maze_rh import MazeRH
from model import Direction

DEBUG = False

# ---------------------- ADB & control ----------------------
device = Device("127.0.0.1", 58526)
device.connect()
controller = Controller(device, DEBUG)
boss = BossDain(controller, DEBUG)

maze = MazeRH(controller, boss, DEBUG)
explorer = Explorer(maze)

# ---------------------- Main loop --------------------------
run = 1
if __name__ == "__main__":
    try:
        while run < 45:
            t0 = time.time()
            # detecting start position
            monetia = cv2.imread("resources/monetia.png", cv2.IMREAD_COLOR)
            monetia_box, _ = find_tpl(maze.get_frame(), monetia, score_threshold=0.9)
            if monetia_box:
                controller._tap((monetia_box["x"], monetia_box["y"]))
                time.sleep(3)

            pub = cv2.imread("resources/pub3.png", cv2.IMREAD_COLOR)
            pub_box, _ = find_tpl(maze.get_frame(), pub, score_threshold=0.9)
            if pub_box:
                controller._tap((pub_box["x"], pub_box["y"]))
                time.sleep(0.5)
                controller._tap((1055, 320))  # hit the enter button
                time.sleep(3)

            if type(boss) is not BossMine and run % 40 == 0:  # every N run
                boss.back()
                controller.flush_bag()
                run = 1
                continue

            boss.tavern_Route()
            boss.portal()

            # explore maze
            isSucces, moves, dir = explorer.run(boss.max_moves, True, boss.debug)
            print(
                f"Run #{run} Explorer finished with: {isSucces}, moves taken: {moves}, time: {time.time() - t0:.1f}s, dir: {dir.label if dir is not None else None}"
            ) if DEBUG else None
            if not isSucces:
                name = f"fails/fail_{time.strftime('%H-%M-%S')}(t-{time.time() - t0:.1f}s).png"
                print(f"----Run #{run}-------------{name}-----------{moves}---X")
                save_image(maze.get_frame(), name)
                if type(boss) is BossMine:
                    raise
                boss.back()
                continue

            # enter gate
            print("Entering gate...") if DEBUG else None
            if dir == Direction.NE:
                controller.move_NE(boss.enter_room_clicks)
            elif dir == Direction.SW:
                controller.move_SW(boss.enter_room_clicks)

            # wait for boss room
            print("Waiting for boss room...") if DEBUG else None
            if not wait_for_boss_popup(
                lambda: maze.get_frame(), timeout_s=10, debug=DEBUG
            ):
                name = f"fails/fake-exit_{time.strftime('%H-%M-%S')}(t-{time.time() - t0:.1f}s).png"
                print(f"----Run #{run}-------------{name}-----------{moves}---X")
                save_image(maze.get_frame(), name)
                if type(boss) is BossMine:
                    raise
                boss.back()
                continue

            controller.yes()
            time.sleep(0.1)

            # fight boss
            hp = boss.start_fight(dir)

            # close summary
            if (
                not wait_for(
                    "resources/figth_end.png",
                    lambda: extract_game(device.get_frame2()),
                    debug=DEBUG,
                )
                or hp != 0
            ):
                print("figth_end not found")
                winsound.Beep(5000, 300)
                time.sleep(60)

            controller.wait_loading(0.5)
            controller.yes()
            controller.wait_loading(0.5)

            # open chest
            if not boss.open_chest(dir) and type(boss) is BossDain:
                print("open chest fail")
                cv2.waitKey(0)
                time.sleep(5)

            name = (
                f"images/run_{time.strftime('%H-%M-%S')}({time.time() - t0:.1f}s).png"
            )
            if moves is not None and moves > 130:
                save_image(maze.get_frame(), name)
            print(f"----Run #{run}-------------{name}-----------{moves}---V")

            run = run + 1
            boss.back()
    finally:
        boss.back() if type(boss) is not BossMine else None
        cv2.destroyAllWindows()
        device.close()
        winsound.Beep(2000, 300)
        print("Finished.")
