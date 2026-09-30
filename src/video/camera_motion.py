"""Background feature motion check for fixed cameras; no ego-motion accuracy claim."""
import cv2
import numpy as np


class CameraMotionGuard:
    def __init__(self, threshold_px=2., hold_seconds=2.):
        self.previous = None
        self.previous_mask = None
        self.threshold = threshold_px
        self.hold = hold_seconds
        self.unsafe_until = -1.

    def update(self, frame, timestamp, boxes=()):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mask = np.full(gray.shape, 255, dtype=np.uint8)
        for box in boxes:
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(mask, (max(0,x1-10),max(0,y1-10)),
                          (min(gray.shape[1],x2+10),min(gray.shape[0],y2+10)), 0, -1)
        result = {'available': False, 'moving': timestamp < self.unsafe_until,
                  'displacement_px': None, 'inliers': 0}
        if self.previous is not None and self.previous.shape == gray.shape:
            points = cv2.goodFeaturesToTrack(self.previous, 160, .02, 12, mask=self.previous_mask)
            if points is not None and len(points) >= 12:
                new, status, _ = cv2.calcOpticalFlowPyrLK(self.previous, gray, points, None)
                if new is not None:
                    good = status.ravel().astype(bool)
                    a, b = points[good].reshape(-1,2), new[good].reshape(-1,2)
                    if len(a) >= 12:
                        matrix, inliers = cv2.estimateAffinePartial2D(a,b,method=cv2.RANSAC,ransacReprojThreshold=2.)
                        if matrix is not None and inliers is not None:
                            count = int(inliers.sum())
                            if count >= 12 and count/len(a) >= .6:
                                h,w = gray.shape
                                anchors = np.array([[0,0,1],[w,0,1],[0,h,1],[w,h,1],[w/2,h/2,1]])
                                displacement = float(np.median(np.linalg.norm(anchors@matrix.T-anchors[:,:2],axis=1)))
                                if displacement > self.threshold: self.unsafe_until = timestamp+self.hold
                                result.update(available=True,moving=timestamp<self.unsafe_until,
                                              displacement_px=displacement,inliers=count)
        self.previous, self.previous_mask = gray, mask
        return result
