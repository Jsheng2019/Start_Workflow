import argparse
import json
import logging
import sys
from typing import Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s: %(message)s")

img_x86_master = 'swr.cn-north-4.myhuaweicloud.com/frameworkptadapter/pytorch_master_a1_x86_64_builder:20260518'
img_x86_v2_6_0 = 'swr.cn-north-4.myhuaweicloud.com/pytorch_images_x86/pytorchx86:v_04'
img_x86_v2_7_1 = 'swr.cn-north-4.myhuaweicloud.com/frameworkptadapter/pytorch_2.7.1_a1_x86_64_builder:20260518'
img_x86_v2_8_0 = 'swr.cn-north-4.myhuaweicloud.com/frameworkptadapter/pytorch_2.8.0_a1_x86_64_builder:20260518'
img_x86_v2_9_0 = 'swr.cn-north-4.myhuaweicloud.com/frameworkptadapter/pytorch_2.9.0_a1_x86_64_builder:20260518'
img_x86_v2_9_1 = 'swr.cn-north-4.myhuaweicloud.com/frameworkptadapter/pytorch_2.9.0_a1_x86_64_builder:20260518'
img_x86_v2_10_0 = 'swr.cn-north-4.myhuaweicloud.com/frameworkptadapter/pytorch_2.10.0_a1_x86_64_builder:20260518'
img_x86_v2_11_0 = 'swr.cn-north-4.myhuaweicloud.com/frameworkptadapter/pytorch_2.11.0_a1_x86_64_builder:20260518'
img_x86_v2_12_0 = 'swr.cn-north-4.myhuaweicloud.com/frameworkptadapter/pytorch_2.12.0_a1_x86_64_builder:20260518'
img_arm_master = 'swr.cn-north-4.myhuaweicloud.com/frameworkptadapter/pytorch_master_a2_aarch64_builder:20260518'
img_arm_v2_6_0 = 'swr.cn-north-4.myhuaweicloud.com/frameworkptadapter/manylinux2_28_aarch64_a2-builder:20260513'
img_arm_v2_7_1 = 'swr.cn-north-4.myhuaweicloud.com/frameworkptadapter/pytorch_2.7.1_a2_aarch64_builder:20260518'
img_arm_v2_8_0 = 'swr.cn-north-4.myhuaweicloud.com/frameworkptadapter/pytorch_2.8.0_a2_aarch64_builder:20260518'
img_arm_v2_9_0 = 'swr.cn-north-4.myhuaweicloud.com/frameworkptadapter/pytorch_2.9.0_a2_aarch64_builder:20260518'
img_arm_v2_9_1 = 'swr.cn-north-4.myhuaweicloud.com/frameworkptadapter/pytorch_2.9.0_a2_aarch64_builder:20260518'
img_arm_v2_10_0 = 'swr.cn-north-4.myhuaweicloud.com/frameworkptadapter/pytorch_2.10.0_a2_aarch64_builder:20260518'
img_arm_v2_11_0 = 'swr.cn-north-4.myhuaweicloud.com/frameworkptadapter/pytorch_2.11.0_a2_aarch64_builder:20260518'
img_arm_v2_12_0 = 'swr.cn-north-4.myhuaweicloud.com/frameworkptadapter/pytorch_2.12.0_a2_aarch64_builder:20260518'


class Img():
    def __init__(self, target_branch, json_path):
        self.target_branch = target_branch
        self.json_path = json_path

    def get_img(self, branch) -> Tuple[str, str]:
        try:
            branch_formatted = branch.split('-')[0].replace(".", "_")
            print(f"分支名： {branch_formatted}")
            x86_img = globals()[f"img_x86_{branch_formatted}"]
            ARM_img = globals()[f"img_arm_{branch_formatted}"]
            return x86_img, ARM_img

        except KeyError:
            print(f"构建镜像失败：未找到分支 [{branch}] 对应的全局变量")
            exit(1)

    def write_img(self, img_1, img_2, json_path):
        total_dict = {
            "x86": img_1,
            "ARM": img_2
        }

        with open(f"{json_path}", "w", encoding="utf-8") as f:
            json.dump(
                total_dict,
                f,
                ensure_ascii=False,
                indent=2
            )

        data = json.load(open(json_path, "r", encoding="utf-8"))
        logging.info(f'json info: {data}')

    def run(self):
        img = self.get_img(self.target_branch)
        self.write_img(img[0], img[1], self.json_path)


if __name__ == "__main__":
    solution = Img(sys.argv[1], sys.argv[2])
    logging.info(f'json path: {sys.argv[2]}')
    solution.run()
