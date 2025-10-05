import logging
import sys
import time
import winsound

import cv2

from boss import (
    BossBhalor,
    BossDain,
    BossDelingh,
    BossElvira,
    BossKhanel,
    BossMine,
    BossKrokust,
    BossTroll,
)
from bot_utils.logger_memory import LastLogsHandler
from bot_utils.screenshoter import save_image
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


# GENERAL TODO:
# improve combat skills CD detection
# improve enemies health bars detection


class BotRunner:
    _boss_map = {
        "krokust": BossKrokust,
        "dain": BossDain,
        "bhalor": BossBhalor,
        "khanel": BossKhanel,
        "delingh": BossDelingh,
        "elvira": BossElvira,
        "troll": BossTroll,
        "mine": BossMine,
    }
    last_logs_handler: LastLogsHandler

    def __init__(self, boss_type: str, debug=False):
        if isinstance(boss_type, str) and boss_type.lower() in self._boss_map:
            boss_class = self._boss_map[boss_type.lower()]
        else:
            raise ValueError(f"Unknown boss type: {boss_type}")

        self.run = 0
        self.failed_runs = 0
        self.consecutive_failed_runs = 0
        self.time_start = time.time()
        self.debug = debug
        self.controller = Controller(
            Device("127.0.0.1", 58526).connect(),
            debug,
        )
        self.boss = boss_class(self.controller, debug)
        self.explorer = Explorer(
            MazeRH(self.controller, self.boss, debug),
        )
        self.last_logs_handler = LastLogsHandler(30)
        logger.addHandler(self.last_logs_handler)
        logger.info(f"Initialized bot for boss: {boss_type}, debug={debug}")

        if debug:
            logger.setLevel(logging.DEBUG)
            logging.getLogger("detect_location").setLevel(logging.DEBUG)
            logging.getLogger("detect_boss_room").setLevel(logging.DEBUG)
            logging.getLogger("controller").setLevel(logging.DEBUG)
            logging.getLogger("devices.device").setLevel(logging.DEBUG)
            logging.getLogger("explorer").setLevel(logging.DEBUG)
            logging.getLogger("sensor").setLevel(logging.DEBUG)
            logging.getLogger("maze_rh").setLevel(logging.DEBUG)
            logging.getLogger("boss.dain").setLevel(logging.DEBUG)
            logging.getLogger("boss.krokust").setLevel(logging.DEBUG)
            logging.getLogger("boss.boss").setLevel(logging.DEBUG)

    def go(self, wait_failed_combat=False):
        logger.info(f"Starting bot... wait_failed_combat={wait_failed_combat}")
        # ---------------------- Main loop --------------------------
        current_run = 0
        while True:
            if self.consecutive_failed_runs >= 6:
                logger.error(
                    f"Too many consecutive failed runs: {self.consecutive_failed_runs}. Stopping bot."
                )
                raise Exception("Too many consecutive failed runs")

            t0 = time.time()
            # detecting start position
            if type(self.boss) is not BossMine:
                self.check_main_map()
                self.check_town()

                # flush bag and back to main map
                if current_run != 0 and current_run % 40 == 0:  # every N run
                    self.boss.back()
                    self.controller.flush_bag(decompose=True)
                    self.controller.full_back()
                    current_run = 0
                    msg = (
                        f"Flush bag: total time: {self.get_total_time()}"
                        f"\nRuns per hour: {self.get_runs_per_hour():.2f}"
                        f"\nFailed runs: {self.failed_runs}/{self.run}"
                    )
                    logger.info(msg)
                    continue

            if not self.boss.tavern_Route():
                self.controller.move_W(4)
                self.boss.back()
                continue

            self.boss.portal()

            # explore maze
            reason, moves, dir = self.explorer.run(
                self.boss.max_moves, True, self.boss.debug
            )
            if reason != "success":
                logger.info(
                    f"❌ #{self.run:03d} t:{time.time() - t0:.1f}s m:{moves:02d} r:{reason}"
                )
                save_image(
                    self.boss._get_frame(),
                    f"fails/{reason}_{time.strftime('%H-%M-%S')}(t-{time.time() - t0:.1f}s).png",
                )
                if type(self.boss) is BossMine:
                    winsound.Beep(2000, 50)
                    raise
                self.boss.back()
                self.failed_runs += 1
                self.consecutive_failed_runs += 1
                continue

            # enter boss gate
            if dir == Direction.NE:
                self.controller.move_NE(self.boss.enter_room_clicks)
            elif dir == Direction.SW:
                self.controller.move_SW(self.boss.enter_room_clicks)

            # wait for boss room
            if not wait_for_boss_popup(self.boss._get_frame, timeout_s=10):
                dir = dir.label if dir is not None else "None"
                logger.info(
                    f"❌ #{self.run:03d} t:{time.time() - t0:.1f}s m:{moves:02d} r:fake exit dir:{dir}"
                )
                save_image(
                    self.boss._get_frame(),
                    f"fails/fake-exit_{time.strftime('%H-%M-%S')}(t-{time.time() - t0:.1f}s)({dir}).png",
                )
                if type(self.boss) is BossMine:
                    winsound.Beep(2000, 70)
                    raise
                self.boss.back()
                self.failed_runs += 1
                self.consecutive_failed_runs += 1
                continue

            self.controller.yes()
            time.sleep(0.1)

            # fight boss
            hp = self.boss.start_fight(dir)

            self.controller.wait_loading()
            # close summary
            if not wait_for(
                "resources/figth_end.png", lambda: extract_game(self.boss._get_frame())
            ):
                save_image(
                    self.boss._get_frame(),
                    f"fails/figth_end_{time.strftime('%H-%M-%S')}.png",
                )
                logger.warning(f"⚠️ figth_end not found, hp left: {hp}%  ")
                if wait_failed_combat:
                    winsound.Beep(2000, 70)
                    cv2.imshow("frame", self.boss._get_frame())
                    cv2.waitKey(0)
                    cv2.destroyAllWindows()

            self.controller.wait_loading(0.5)
            self.controller.yes()
            self.controller.wait_loading(0.5)

            # open chest
            if not self.boss.open_chest(dir) and type(self.boss) is BossDain:
                logger.warning("⚠️ open chest fail")
                if wait_failed_combat:
                    winsound.Beep(2000, 70)
                    cv2.imshow("frame", self.boss._get_frame())
                    cv2.waitKey(0)
                    cv2.destroyAllWindows()

            if moves is not None and moves > 130:
                save_image(
                    self.boss._get_frame(),
                    f"images/run_{time.strftime('%H-%M-%S')}({time.time() - t0:.1f}s).png",
                )

            # success resets consecutive failed counter
            self.consecutive_failed_runs = 0
            current_run += 1
            self.run += 1
            logger.info(f"✅ #{self.run:03d} t:{time.time() - t0:.1f}s m:{moves}")
            self.boss.back()

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

    def get_runs_per_hour(self):
        elapsed_time = time.time() - self.time_start
        if elapsed_time == 0:
            return 0.0
        runs_per_hour = (self.run / elapsed_time) * 3600
        return runs_per_hour

    def get_total_time(self):
        elapsed_time = time.time() - self.time_start
        hours = int(elapsed_time // 3600)
        minutes = int((elapsed_time % 3600) // 60)
        seconds = int(elapsed_time % 60)
        return f"{hours:02}:{minutes:02}:{seconds:02}"

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
    if len(sys.argv) > 1:
        boss_arg = sys.argv[1]
        wait_failed_combat = len(sys.argv) > 2 and sys.argv[2].lower() == "true"
        debug = False
    else:
        # krokust | dain | bhalor | khanel | delingh | elvira | mine | troll
        boss_arg = "dain"
        debug = True
        wait_failed_combat = True

    BotRunner(boss_arg, debug).go(wait_failed_combat)
