import sys
from copy import deepcopy
import time

import rospy
import tf
from std_msgs.msg import Header
from geometry_msgs.msg import (
    PoseStamped,
    Pose,
    Point,
    Twist,
    Quaternion,
)

import baxter_interface
from baxter_core_msgs.srv import (
    SolvePositionIK,
    SolvePositionIKRequest,
)


class ArmController(object):

    def __init__(self, limb, starting_pos=None, push_thresh=30):
        self.neutral_pos = starting_pos
        self.push_thresh = push_thresh
        rospy.init_node("baxter_myo")
        rospy.Subscriber("myo_data", Twist, self.callback)
        rospy.loginfo("Subscribed to myo_data")

        self.data = Twist()
        self.name_limb = limb
        self.limb = baxter_interface.Limb(self.name_limb)
        rospy.loginfo("Enabling Baxter...")
        self._rs = baxter_interface.RobotEnable(baxter_interface.CHECK_VERSION)
        self._rs.enable()
        # TODO add tucking

        self.received = False
        self.baxter_off = Twist()
        rospy.loginfo("Moving to starting position...")
        self.move_to_neutral()
        rospy.loginfo("Recording offset...")
        self.set_offset()

    def callback(self, data):
        self.received = True
        self.data = deepcopy(data)
        # rospy.loginfo(rospy.get_caller_id() + " heard: \
        # \n Linear [%f, %f, %f] \
        # \n Angular [%f, %f, %f]",
        #               self.data.linear.x, self.data.linear.y,
        #               self.data.linear.z, self.data.angular.x,
        #               self.data.angular.y, self.data.angular.z)

    def move_to_neutral(self):
        self.limb.move_to_joint_positions(self.neutral_pos)

    def set_offset(self):
        pose = self.limb.endpoint_pose()
        eu = tf.transformations.euler_from_quaternion(pose['orientation'])
        self.baxter_off.linear.x = pose['position'][0]
        self.baxter_off.linear.y = pose['position'][1]
        self.baxter_off.linear.z = pose['position'][2]
        self.baxter_off.angular.x = eu[0]
        self.baxter_off.angular.y = eu[1]
        self.baxter_off.angular.z = eu[2]

    def get_effort(self):
        e = self.limb.joint_efforts()
        s = sum([abs(e[i]) for i in e.keys()])
        return s

    def is_pushing(self):
        e = self.get_effort()
        return e > self.push_thresh


    def find_joint_position(self, pose, x_off=0.0, y_off=0.0, z_off=0.0):
        '''
        Finds the joint position of the arm given some pose and the
        offsets from it (to avoid opening the structure all the time
        outside of the function).
        '''
        ik_srv = "ExternalTools/right/PositionKinematicsNode/IKService"
        iksvc = rospy.ServiceProxy(ik_srv, SolvePositionIK)
        ik_request = SolvePositionIKRequest()
        the_pose = deepcopy(pose)
        the_pose['position'] = Point(x=pose['position'].x + x_off,
                                     y=pose['position'].y + y_off,
                                     z=pose['position'].z + z_off)
        approach_pose = Pose()
        approach_pose.position = the_pose['position']
        approach_pose.orientation = the_pose['orientation']
        hdr = Header(stamp=rospy.Time.now(), frame_id='base')
        pose_req = PoseStamped(header=hdr, pose=approach_pose)
        ik_request.pose_stamp.append(pose_req)
        resp = iksvc(ik_request)
        return dict(zip(resp.joints[0].name, resp.joints[0].position))

    def find_joint_pose(self, pose, targ_x=0.0, targ_y=0.0, targ_z=0.0,
                        targ_ox=0.0, targ_oy=0.0, targ_oz=0.0):
        '''
        WRITE_ME
        '''
        ik_srv = "ExternalTools/right/PositionKinematicsNode/IKService"
        iksvc = rospy.ServiceProxy(ik_srv, SolvePositionIK)
        ik_request = SolvePositionIKRequest()
        the_pose = deepcopy(pose)
        the_pose['position'] = Point(x=targ_x + self.baxter_off.linear.x,
                                     y=targ_y + self.baxter_off.linear.y,
                                     z=targ_z + self.baxter_off.linear.z)
        angles = tf.transformations.quaternion_from_euler(
            targ_ox + self.baxter_off.angular.x,
            targ_oy + self.baxter_off.angular.y,
            targ_oz + self.baxter_off.angular.z)
        the_pose['orientation'] = Quaternion(x=angles[0],
                                             y=angles[1],
                                             z=angles[2],
                                             w=angles[3])
        approach_pose = Pose()
        approach_pose.position = the_pose['position']
        approach_pose.orientation = the_pose['orientation']
        hdr = Header(stamp=rospy.Time.now(), frame_id='base')
        pose_req = PoseStamped(header=hdr, pose=approach_pose)
        ik_request.pose_stamp.append(pose_req)
        try:
            resp = iksvc(ik_request)
            return dict(zip(resp.joints[0].name, resp.joints[0].position))
        except:
            return None

    def move_loop(self):
        while not rospy.is_shutdown():
            if self.received:
                new_poss = self.find_joint_pose(
                    self.limb.endpoint_pose(),
                    targ_x=float(self.data.linear.x),
                    targ_y=float(self.data.linear.y),
                    targ_z=float(self.data.linear.z),
                    targ_ox=float(self.data.angular.x),
                    targ_oy=float(self.data.angular.y),
                    targ_oz=float(self.data.angular.z))
                rospy.loginfo("Position sent!")
                self.limb.move_to_joint_positions(new_poss, timeout=0.1)
                self.received = False
                if self.is_pushing():
                    rospy.loginfo("PUSHING!!!")



def main():
    ac = ArmController('right')
    ac.move_loop()

if __name__ == "__main__":
    sys.exit(main())
