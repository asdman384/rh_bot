import logging
import time
import winsound

import cv2

from boss import BossDelingh, BossMine, BossDain, BossKhanel, BossBhalor, BossElvira
from bot_utils.screenshoter import save_image
from bot_utils.logger_memory import LastLogsHandler
from controller import Controller
from detect_boss_room import wait_for_boss_popup
from detect_location import find_tpl, wait_for
from devices.device import Device
from explorer import Explorer
from frames import extract_game
from maze_rh import MazeRH
from model import Direction

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(module)s %(levelname)s: %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)
# logging.getLogger("boss.dain").setLevel(logging.DEBUG)
# logging.getLogger("boss.boss").setLevel(logging.DEBUG)


class BotRunner:
    _boss_map = {
        "dain": BossDain,
        "bhalor": BossBhalor,
        "khanel": BossKhanel,
        "delingh": BossDelingh,
        "elvira": BossElvira,
        "mine": BossMine,
    }
    last_logs_handler: LastLogsHandler

    def __init__(self, boss_type: str, debug=False):
        # check if boss_type in boss_map
        if isinstance(boss_type, str) and boss_type.lower() in self._boss_map:
            boss_class = self._boss_map[boss_type.lower()]
        else:
            raise ValueError(f"Unknown boss type: {boss_type}")

        self.run = 1
        self.debug = debug
        self.controller = Controller(
            Device("127.0.0.1", 58526).connect(),
            debug,
        )
        self.boss = boss_class(self.controller, debug)
        self.explorer = Explorer(
            MazeRH(self.controller, self.boss, debug),
        )
        logger.info(f"Initialized bot for boss: {boss_type}")

        self.last_logs_handler = LastLogsHandler(30)
        logger.addHandler(self.last_logs_handler)

    def check_main_map(self):
        monetia = cv2.imread("resources/monetia.png", cv2.IMREAD_COLOR)
        monetia_box, _ = find_tpl(self.boss._get_frame(), monetia, score_threshold=0.9)
        if monetia_box:
            self.controller._tap((monetia_box["x"], monetia_box["y"]))
            time.sleep(3)

    def check_town(self):
        pub = cv2.imread("resources/pub3.png", cv2.IMREAD_COLOR)
        pub_box, _ = find_tpl(self.boss._get_frame(), pub, score_threshold=0.9)
        if pub_box:
            self.controller._tap((pub_box["x"], pub_box["y"]))
            time.sleep(0.5)
            self.controller._tap((1055, 320))  # hit the enter button
            time.sleep(3)

    def go(self):
        # ---------------------- Main loop --------------------------
        current_run = 1
        while current_run < 45:
            t0 = time.time()
            # detecting start position
            self.check_main_map()
            self.check_town()

            # flush bag and back to main map
            if type(self.boss) is not BossMine and current_run % 40 == 0:  # every N run
                self.boss.back()
                self.controller.flush_bag(decompose=True)
                self.controller.full_back()
                current_run = 1
                continue

            self.boss.tavern_Route()
            self.boss.portal()

            # explore maze
            reason, moves, dir = self.explorer.run(
                self.boss.max_moves, True, self.boss.debug
            )
            if reason != "success":
                logger.info(
                    f"❌ - Run #{self.run:03d} - t:{time.time() - t0:.1f}s - m:{moves} - r:{reason}"
                )
                save_image(
                    self.boss._get_frame(),
                    f"fails/{reason}_{time.strftime('%H-%M-%S')}(t-{time.time() - t0:.1f}s).png",
                )
                if type(self.boss) is BossMine:
                    winsound.Beep(2000, 50)
                    raise
                self.boss.back()
                continue

            # enter boss gate
            if dir == Direction.NE:
                self.controller.move_NE(self.boss.enter_room_clicks)
            elif dir == Direction.SW:
                self.controller.move_SW(self.boss.enter_room_clicks)

            # wait for boss room
            if not wait_for_boss_popup(
                self.boss._get_frame, timeout_s=10, debug=self.debug
            ):
                logger.info(
                    f"❌ - Run #{self.run:03d} - t:{time.time() - t0:.1f}s - m:{moves} - r:fake exit"
                )
                save_image(
                    self.boss._get_frame(),
                    f"fails/fake-exit_{time.strftime('%H-%M-%S')}(t-{time.time() - t0:.1f}s).png",
                )
                if type(self.boss) is BossMine:
                    winsound.Beep(2000, 50)
                    raise
                self.boss.back()
                continue

            self.controller.yes()
            time.sleep(0.1)

            # fight boss
            hp = self.boss.start_fight(dir)

            self.controller.wait_loading()
            # close summary
            if (
                not wait_for(
                    "resources/figth_end.png",
                    lambda: extract_game(self.boss._get_frame()),
                    debug=self.debug,
                )
                or hp != 0
            ):
                logger.warning("⚠️ figth_end not found")
                winsound.Beep(5000, 300)
                time.sleep(60)

            self.controller.wait_loading(0.5)
            self.controller.yes()
            self.controller.wait_loading(0.5)

            # open chest
            if not self.boss.open_chest(dir) and type(self.boss) is BossDain:
                logger.warning("⚠️ open chest fail")
                winsound.Beep(5000, 300)
                time.sleep(30)

            if moves is not None and moves > 130:
                save_image(
                    self.boss._get_frame(),
                    f"images/run_{time.strftime('%H-%M-%S')}({time.time() - t0:.1f}s).png",
                )

            logger.info(
                f"✅ - Run #{self.run:03d} - t:{time.time() - t0:.1f}s - m:{moves}"
            )

            current_run += 1
            self.run += 1
            self.boss.back()

    def __del__(self):
        cv2.destroyAllWindows()
        if hasattr(self, "last_logs_handler"):
            logger.removeHandler(self.last_logs_handler)
            self.last_logs_handler.close()
        # Destructor: clean up resources if needed
        if hasattr(self, "controller") and hasattr(self.controller, "device"):
            self.controller.device.close()
        logger.info("Finished.")


if __name__ == "__main__":
    BotRunner("delingh").go()
