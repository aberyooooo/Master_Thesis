# -*- coding: utf-8 -*-
"""強化学習を使って自動運転をシミュレーションしてみた話 ソースコード.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1FBOfvz5AIomncvHax5E3TFrkMEOePNxh
"""

import torch
from torch import tensor
import numpy as np
from numpy import array, cos, sin, tan, arctan2
import math
import matplotlib.pyplot as plt





class Car:
    """
    自動車の状態を表すクラス
    
    Attributes
    --------------------
    params: dict
        自動車の状態を保存したリスト
    dpos: np.array
        直前の更新で自動車が移動したベクトル
    step_dis: float
        直前の更新で自動車が進んだ距離
    total_dis: float
        自動車が進んだ距離の合計
    """

    def __init__(self, *args, **kwargs):
        """
        自動車の初期状態を読み込む
        
        Parameters
        --------------------
        x, y: float
            自動車のx座標、y座標
        yaw: float
            自動車のx軸からの角度 [rad]
        vx, vy: float
            自動車の速度のx成分、y成分
            自動車の向いている方向がx方向、そこから反時計回りに90度回転した方向がy方向
        """
        # 自動車の状態を初期化
        self._params_name = ["x", "y", "yaw", "vx", "vy", "v", "a", "s", "pos", "time", "dt"]
        self.params = dict(zip(self._params_name, [np.array(0)]*len(self._params_name)))
        for key, var in kwargs.items():
            self.params[key] = np.array(var)
        self._params_update(self.params)
        
        # 時間履歴の作成
        self._histories = dict(zip(self._params_name, [0]*len(self._params_name)))
        for param in self._params_name:
            if param == "pos": continue
            self._histories[param] = self.params[param].reshape(1)
        self._histories["pos"] = self.params["pos"].reshape(1,-1)
        self._histories["dt"] = np.array([0])
        self._histories["a"] = np.array([])
        self._histories["s"] = np.array([])

        self._nparams = dict()
        self.total_dis = 0

    def update(self, a, steer, dt):
        """
        自動車の状態を更新する関数
        
        Parameters
        --------------------
        a: float
            自動車の加速度（＝アクセルやブレーキの踏み込み量）
        steer: float
            自動車の時間当たりの回転角（＝ステアリング角度）
        dt: float
            1ステップの時間間隔
        """
        # 引数を辞書に格納
        self.params["a"] = np.array(a)
        self.params["s"] = np.array(steer)
        self.params["dt"] = np.array(dt)
        self.params["time"] = self.params["time"] + self.params["dt"]

        # 状態の更新
        self._model()

        # 変数のアップデート
        npos = np.concatenate([self._nparams["x"].reshape(1), self._nparams["y"].reshape(1)])
        self.dpos = np.concatenate([self.params["pos"].reshape(1, -1), npos.reshape(1, -1)])
        self.step_dis = distance(*self.dpos)
        self.total_dis += self.step_dis
        self._params_update(self._nparams)
        self._params_history_update()
    
    def _model(self):
        """
        次のステップの自動車の状態を求める関数
        """
        self.params["time"] = self.params["time"] + self.params["dt"]
        self._nparams["x"] = self.params["x"] + self.params["vx"]*cos(self.params["yaw"])*self.params["dt"]
        self._nparams["y"] = self.params["y"] + self.params["vx"]*sin(self.params["yaw"])*self.params["dt"]
        self._nparams["vx"] = self.params["vx"] + self.params["a"]*self.params["dt"]
        self._nparams["yaw"] = self.params["yaw"] + self.params["s"]*self.params["dt"]

    def _params_update(self,new_params):
        """
        自動車の状態を更新後、変数を更新する関数
        
        Parameters
        --------------------
        new_params: dict
            次のステップでの自動車の状態を格納した辞書
        """
        for param in new_params.keys():
            self.params[param] = new_params[param].reshape(1)
        self.params["pos"] = np.concatenate([self.params["x"].reshape(1), self.params["y"].reshape(1)])
        self.params["v"] = np.sqrt(self.params["vx"]**2 + self.params["vy"]**2).reshape(1)

    def _params_history_update(self):
        """
        自動車の状態を更新後、履歴を更新する関数
        """
        for param in self._params_name:
            if param == "pos": continue
            self._histories[param] = np.concatenate([self._histories[param], self.params[param].reshape(1)])
        self._histories["pos"] = np.concatenate([self._histories["pos"], self.params["pos"].reshape(1,-1)])

    def trajectory_onplot(self):
        """
        自動車の軌跡を描く関数
        """
        plt.plot(self._histories["x"], self._histories["y"])
    

def distance(pos1, pos2):
    """
    2点間の距離を求める関数

    Parameters
    ---------------------
    pos1, pos2: list of float
        距離を求める2点
    
    Returns
    --------------------
    res: float
        求めた2点間の距離
    """
    delta = (pos1-pos2)**2
    res = np.sqrt(delta[0]+delta[1])
    return res

import numpy as np
import math

class LiDAR:
    """
    LiDARを定義するクラス
    
    Attributes
    ----------
    sensor_angles_std: list of float
        自動車の進行方向に対するLiDARの角度 [rad]
    line_delta: float
        センサの１点の間隔（センサの解像度と同義）
    line_num: int
        LiDARの点の数
    """
    
    def __init__(self, car, sensor_angle_max=180, sensor_num=31, line_len=30, line_delta=0.1):
        """
        Parameters
        ----------
        car: Car
            LiDARを乗せる自動車
        sensor_angle_max: float of float
            LiDARを出す最大の角度 [deg]
        sensor_num: int
            LiDARの本数
        line_len: float
            LiDARの届く長さ
        line_delta: float
            LiDARの1点の間隔
        """
        # 自動車の進行方向に対するセンサの角度を求めていく
        sensor_angle_min = -sensor_angle_max/2  # 自動車から見た角度の最小値
        sensor_angle_delta = sensor_angle_max / (sensor_num-1)  # 隣接するセンサ同士の角度
        sensor_angles_std = []
        self.sensor_num = sensor_num
        for i in range(sensor_num):
            sensor_angle_i = sensor_angle_min + sensor_angle_delta * i  # 右からi番目のセンサの角度
            sensor_angles_std += [sensor_angle_i]
        
        # 作成したものをクラスのメンバにしていく
        self.sensor_angles_std = np.deg2rad(np.array(sensor_angles_std))
        self.line_len = line_len
        self.line_num = int((line_len+line_delta) / line_delta)
        self.line_delta = line_delta

        self.car = car


    def make_line(self, map):
        """
        LiDARから出てきたレーダーのラインを作り、壁との距離を求める
        
        Parameters
        ----------
        map: MAP
            道路を記述したクラス
        
        Returns
        ----------
        line_end_pos: list of float
            センサ端点の座標
        line_reaches_wall: list of bool
            センサが壁に到達しているか判断するリスト
        """

        # 自動車の位置と角度を取り出す
        pos = self.car.params['pos']
        yaw = self.car.params['yaw']

        # センサのx軸からの角度を求める
        sensor_angles = self.sensor_angles_std + yaw
        line_reaches_wall = [False]*self.sensor_num
        line_end_pos = np.empty([0, 2])
        line_distaces = []

        for i, sensor_angle in enumerate(sensor_angles):
            # sensor_angle: 自動車から見て右からi番目のセンサの角度
            # センサの端点を求める
            cos_angle = math.cos(sensor_angle)
            sin_angle = math.sin(sensor_angle)
            line_end_xy = pos + np.array([cos_angle, sin_angle])*self.line_len
            sensor_line = np.concatenate([line_end_xy.reshape(1, -1), pos.reshape(1, -1)])

            line_dis = self.line_len    # 壁を認識する範囲の最大値を、壁までの距離の初期値とする
            flag, points = map.is_collision(sensor_line)    # センサが壁に衝突したかを判断
            if flag:    # センサが壁にぶつかったら
                line_reaches_wall[i] = True  # 衝突したというフラグを立てる
                for p in points:
                    dis = distance(pos, p)          # 壁から自動車までの距離を求める
                    if dis < line_dis:  # 壁から自動車の距離が今までのよりも近かったら
                        line_dis = dis  # この距離を壁までの距離とする
                        point = p
            else:       # センサの届く範囲に壁がなかったら
                point = line_end_xy     # センサの端点を壁のある点とする

            # 壁の位置またはセンサの端点を格納
            line_end_pos = np.concatenate([line_end_pos, point.reshape(1,-1)])
            # 自動車から壁までの距離をリストに格納
            line_distaces.append(line_dis)
        line_distaces = np.array(line_distaces)
        return line_end_pos, line_reaches_wall, line_distaces

class MAP:
    """
    道路を記述するクラス
    
    Atrributes
    ----------
    line: list of float
        道路の端点を格納したリスト
    
    """
    def __init__(self, walls):
        """
        Parameters
        ----------
        walls: list of float
            道路の頂点を格納したリスト
        """
        wall_lines = []
        for wall_vertices in walls:
            # wall_vertices: 一筆書きができるような壁の集まり
            wall_line = [[pos1, pos2] for pos1, pos2 in zip(wall_vertices[:-1], wall_vertices[1:])]
            wall_lines += wall_line
        
        self.lines = np.array(wall_lines)

    def onplot(self):
        """
        道路の線を描画する
        """
        for line in self.lines:
            plt.plot(*line.T, color='green')
    
    def is_collision(self, line):
        """
        道路の壁にぶつかるか判定する

        Parameters
        ----------
        line: list of float
            壁と交差しているか判定したい線分の端点
        
        Returns
        ----------
        cross_points: list of float
            壁との交点を格納したリスト
        """
        cross_points = np.empty([0, 2])
        res_flag = False
        for road_line in self.lines:
            flag, cross_point = crossing(road_line, line)     # 線分が交差しているか確認
            if flag:
                res_flag = True
                # 交差していたらその座標を交点を格納するリストに追加
                cross_points = np.concatenate([cross_points, cross_point.reshape(1, -1)])
        return res_flag, cross_points


def crossing(line1, line2):
    """
    2直線の交点を求め、交差しているかを判定する
    
    Parameters
    ----------
    line1, line2: list of float
        直線の端点
    
    Returns
    ----------
    flag: bool
        直線上にあったらTrue、なかったらFalseを返す
    cross_point: list of float
        交点、交差していなかったら(0, 0)を返す
    """
    flag, cross_point = cal_crosspoint(line1, line2)

    if not is_online(line1, cross_point):
        flag = False
    if not is_online(line2, cross_point):
        flag =  False
    return flag, cross_point


def cal_crosspoint(line1, line2):
    """
    2直線の交点を求める
    
    Parameters
    --------------------
    line1, line2: list of float
        直線の端点
    
    Returns
    --------------------
    flag: bool
        交差していたらTrue, 平行だったらFalseを返す
    cross_point: list of float
        交点、平行だったら(0, 0)を返す
    """
    A, B = line1
    C, D = line2

    x1, y1 = A
    x2, y2 = B
    x3, y3 = C
    x4, y4 = D

    flag = True
    if x1 == x2 and x3 == x4:   # ABとCDがどちらもy軸に平行のとき
        x, y = 0, 0
        flag = False
    elif x1 == x2:  # ABがy軸に平行のとき
        x = x1
        y = (y4 - y3)/(x4 - x3)*(x1 - x3) + y3
    elif x3 == x4:  # CDがy軸に平行のとき
        x = x3
        y = (y2 - y1)/(x2 - x1)*(x3 - x1) + y1
    else:   # ABもCDもy軸に平行ではないとき
        a1 = (y2 - y1)/(x2 - x1)    # ABの傾き
        a3 = (y4 - y3)/(x4 - x3)    # CDの傾き
        if a1 == a3:    # ABとCDが平行のとき
            x, y = 0, 0
            flag = False
        else:           # ABとCDが平行ではないとき
            x = (a1*x1 - y1 - a3*x3 + y3)/(a1 - a3)
            y = (y2 - y1)/(x2 - x1)*(x - x1) + y1
    return flag, np.array([x, y])


def is_online(line, pos):
    """
    点(pos)が線分(line)上にあるか判定する
    
    Parameters
    ----------
    line: list of float
        直線の端点
    pos: list of float
        点の座標
    
    Returns
    -----------
    res: bool
        点が線分上にあったらTrue、なかったらFalseを返す
    """
    pos1, pos2 = line
    # posが線分の端点のどちらかと同じだったら pos はline1上にある
    # ここではそれぞれの座標の差が 1e-5 以下なら同じ点とみなす
    
    if all(abs(pos1-pos)<=1e-5) or all(abs(pos2-pos)<=1e-5):
        return True
    
    # posが直線上に載っているか確認、posから線分の端点への直線の傾きが一致しないとposは直線上にない
    # dy1/dx1 == dy2/dx2 => dy1*dx2 == dy2*dx1
    # ここでは dy1*dx2 と dy2*dx1 の差が 1e-5 以上なら傾きが一致していないとみなす
    if abs(((pos1-pos)[1]*(pos2-pos)[0] - (pos1-pos)[0]*(pos2-pos)[1])) >= 1e-5:
        return False
    
    # pos1からみたposとposから見たpos2が同じ方向にあるか確認
    # pos1-posとpos-pos2の符号が一致すればよい
    # if all((np.sign(pos1-pos)*(abs(pos1-pos)>1e-5)) == (np.sign(pos-pos2)*(abs(pos-pos2)>1e-5))):
    if all((np.sign(pos1-pos)) == (np.sign(pos-pos2))):
        return True
    else:
        return False

"""実際に走らせる"""

import random
import torch.nn as nn
import torch.nn.functional as F
from torch import optim


class NeuralNetwork(nn.Module):
    """
    方策を決めるNeuralNetwork
    """
    def __init__(self, dim_in, dim_out):
        super().__init__()
        self.seq = nn.Sequential(
            nn.Linear(dim_in, NUM_HIDDEN_NODES),
            nn.Tanh(),
            nn.Linear(NUM_HIDDEN_NODES, dim_out)
        )
    
    def forward(self, x):
        return F.softmax(self.seq(x), dim=0)


def dicide_action(output):
    """
    NeuralNetworkの出力から行動を決定する関数
    
    Parameters
    ---------------------
    output: tensor
        NeuralNetworkからの出力
    
    Returns
    --------------------
    action: dict
        とった行動
    one_hot: list
        とった行動のone-hotベクトル
    """
    prop = output.detach().numpy()
    one_hot = torch.zeros([NUM_ACTIONS])
    
    # 行動を確率をもとに曲がる方向と加速度を選択
    action = np.random.choice(range(NUM_ACTIONS), p=prop)  
    one_hot[action] = 1

    # 行動を決定
    steer, a = ACTION_LIST[action]
    steer *= np.deg2rad(steer_step)
    action = dict()
    action["steer"] = steer
    action["a"] = a
    action["dt"] = 0.1
    return action, one_hot


def episode(car, lidar, Map, model, vis=False):
    """
    1エピソード進める関数
    
    Parameters
    --------------------
    car: Car
        自動車の状態を記述したクラス
    lidar: LiDAR
        LiDARを記述したクラス
    Map: MAP
        道路の情報を記述したクラス
    model: NeuralNetwork
        行動を決めるためのNeuralNetwork
    vis: bool
        可視化フラグ

    Returns
    --------------------
    experiences: list of dict
        各ステップの情報
    rewards: tensor
        各エピソードにおける各時刻の報酬を格納したリスト
        サイズは [num_episode, max_number_of_steps]
        エピソードの長さが max_number_of_steps に満たない場合は nan を格納
    policies: tensor
        各エピソードにおける各時刻の方策を格納したリスト
        サイズは [num_episode, max_number_of_steps]
        実際にとった行動をとる確率を格納
        エピソードの長さが max_number_of_steps に満たない場合は nan を格納
    step: int
        エピソードの長さ
    """

    experiences = []        # 各ステップを格納するリスト
    done = False            # エピソード終了のフラグ
    collision_reward = 0    # ぶつかった時の報酬
    step = 0                # ステップ数

    pi_list = tensor([np.nan]*max_number_of_steps)      # 方策を格納するリスト
    reward_list = tensor([np.nan]*max_number_of_steps)  # 報酬を格納するリスト
    
    while done == False:
        # 壁の点、ラインが壁にぶつかったか、壁までの距離を取得
        points, flags, distances = lidar.make_line(Map)
        
        # NeuralNetworkに入れるように各変数をtensorに変換
        distances = torch.tensor(distances).float()
        vx = torch.tensor(car.params['vx']).float()
        input = torch.cat([distances, vx])
        
        step_dict = {}

        # 行動を決定して自動車を動かし報酬を得る
        output = model(input)
        action, one_hot = dicide_action(output)
        car.update(**action)
        reward = car.step_dis     # 1stepに進んだ距離を報酬にする
        
        if vis:
            plt.axis("equal")
            car.trajectory_onplot()
            Map.onplot()
            plt.show()

            print("input:  {}".format(distances))
            print("output: {}".format(output))
        
        # ぶつかったか確認
        collision_flag, collision_point = Map.is_collision(car.dpos)
        if collision_flag:
            # ぶつかったら終了
            # このときのステップ報酬は collision_reward になる
            reward = collision_reward
            done = True
        
        if len(experiences) >= max_number_of_steps-1:
            # 最大ステップ数に達したら終了
            done = True

        # ステップの情報を辞書に格納
        step_dict["state"] = distances  # 自動車から壁までの距離
        step_dict["output"] = output    # NeuralNetworkからの出力
        step_dict["reward"] = reward    # このステップの報酬
        step_dict["action"] = action    # 実際にとった行動
        step_dict["one_hot"] = one_hot  # とった行動を1、それ以外を0としてリストに格納
        step_dict["done"] = done        # 終了フラグ
        experiences.append(step_dict)   # このステップの情報をリストに追加

        # 今回の行動をとる確率を算出し記録
        pi_list[step] = step_dict["output"]@step_dict["one_hot"]
        # 即時報酬を記録
        reward_list[step] = step_dict["reward"]
        step += 1
        
    return experiences, pi_list.reshape(1,-1), reward_list.reshape(1,-1), step


def update_policy(rewards, policies, steps, opt):
    """
    方策を更新する関数
    
    Parameters
    --------------------
    rewards: tensor
        各エピソードにおける各時刻の報酬を格納したリスト
        サイズは [num_episode, max_number_of_steps]
        エピソードの長さが max_number_of_steps に満たない場合は nan を格納
    policies: tensor
        各エピソードにおける各時刻の方策(実際にとった行動をとる確率)を格納したリスト
        サイズは [num_episode, max_number_of_steps]
        エピソードの長さが max_number_of_steps に満たない場合は nan を格納
    steps: tensor
        各エピソードの長さを格納したリスト
        サイズは [num_episode]
    opt: optimizer
    """
    
    # 報酬の平均を算出
    reward_ave = (rewards.nansum(dim=1)/steps).mean()

    # 方策(ここではpolicies)にlogをかけてrewardをかける
    clampped = torch.clamp(policies, 1e-10, 1)    # log(0)を避ける
    Jmt = clampped.log()*(rewards-reward_ave)
    
    # 平均を取る
    J = (Jmt.nansum(dim=1)/steps).mean()    # [num_episode, max_number_of_steps] -> [1]

    # 方策の更新
    J.backward()
    opt.step()
    opt.zero_grad()


# 道路の情報
# ロ字型
in_vertices = [[30,30],[-30,30],[-30,-30],[30,-30],[30,30]]
out_vertices = [[40,40],[-40,40],[-40,-40],[40,-40],[40,40]]
# 自動車の初期値(ロ字型)
x0 = 30
y0 = 0
yaw0 = 90
verocity = 6


"""分岐ありの結果は、以下のコメントアウトを外して実行してください"""
# # T字型
# in_vertices = [[5,-60],[5,-40],[40,-40],[40,40],[-40,40],[-40,-40],[-5,-40],[-5,-60]]
# out_vertices = [[30,-30],[30,30],[-30,30],[-30,-30],[30,-30]]
# # 自動車の初期値(T字型)
# x0 = 0
# y0 = -60
# yaw0 = 90
# verocity = 6


walls = [in_vertices, out_vertices, ]
Map = MAP(walls)

epochs = 50
num_episode = 50
max_number_of_steps = 200

# 自動車の制御方法
direction_list = [1, 0.5, 0, -0.5, -1]
acceleration_list = [1, 0.5, 0, -0.5, -1]
ACTION_LIST = [(d, a) for d in direction_list for a in acceleration_list]
steer_step = 90
acceleration_step = 1

sensor_num = 15
dim_in = sensor_num + 1 # sensorと速度
NUM_ACTIONS = len(ACTION_LIST)
NUM_HIDDEN_NODES = 32
lr = 0.01

mean_reward_list = np.zeros((0,1))

model = NeuralNetwork(dim_in=dim_in, dim_out=NUM_ACTIONS)
opt = optim.Adam(model.parameters(), lr=lr)

car_list = []
reward_list = np.zeros((0))
mean_reward_list = np.zeros((0))

for epoch in range(epochs):
    """
    experiences: list
        各エピソードの中身を格納したリスト
        サイズは [num_episodes, episode length]
        エピソード内の1ステップの中身は dict 型で格納
    rewards: tensor
        各エピソードにおける各時刻の報酬を格納したリスト
        サイズは [num_episode, max_number_of_steps]
        エピソードの長さが max_number_of_steps に満たない場合は nan を格納
    policies: tensor
        各エピソードにおける各時刻の方策(実際に選択した行動をとる確率)を格納したリスト
        サイズは [num_episode, max_number_of_steps]
        エピソードの長さが max_number_of_steps に満たない場合は nan を格納
    steps: tensor
        各エピソードの長さを格納
        サイズは [num_episode]
    """
    experiences = []
    rewards = tensor([])
    policies = tensor([])
    steps = tensor([])

    for m in range(num_episode):
        # 自動車の初期状態を作成
        x = x0+random.random()
        y = y0+random.random()
        yaw = yaw0+random.random()
        yaw = np.deg2rad(yaw)

        # CarオブジェクトとLiDARオブジェクトを作成
        car = Car(x=x, y=y, yaw=yaw, vx=verocity)
        lidar = LiDAR(car=car, sensor_num=sensor_num)

        # 実際に走らせる
        episode_experience, pi_list, episode_reward, step = episode(car, lidar, Map, model)

        # 結果をそれぞれ格納
        experiences.append(episode_experience)          # エピソード
        policies = torch.cat([policies, pi_list])       # 方策
        rewards = torch.cat([rewards, episode_reward])  # 報酬
        steps = torch.cat([steps, tensor([step])])      # 各エピソードの長さ
        
        reward_list = np.concatenate([reward_list, episode_reward.nansum().numpy().reshape(1)])
    
    car = Car(x=x, y=y, yaw=yaw, vx=verocity)
    lidar = LiDAR(car=car, sensor_num=sensor_num)
    episode_experience, pi_list, episode_reward, step = episode(car, lidar, Map, model)
    car_list += [car]
    print("{} epoch: {}".format(epoch, episode_reward.nansum()))
    print("average_reward: {}".format((rewards.nansum(dim=1)).mean()))

    mean_reward_list = np.concatenate([mean_reward_list, (rewards.nansum(dim=1)).mean().reshape(1)])

    update_policy(rewards, policies, steps, opt)

def env_visualize(*cars):
    fig = plt.figure()
    plt.axis("equal")
    Map.onplot()
    for car in cars:
        car.trajectory_onplot()
    plt.show()

vis_freq = 10

for i in range(epochs//vis_freq):
    env_visualize(*car_list[i*vis_freq:(i+1)*vis_freq])
env_visualize(*car_list)

plt.plot(mean_reward_list)
plt.show()