"""Optional normalized road plane and expected-movement corridors."""
import cv2
import numpy as np


class RoadCalibration:
    def __init__(self, config):
        self.corridors = config.get('corridors', [])
        self.matrix = None
        self.units = 'image pixels'
        if config.get('image_points') or config.get('road_points'):
            image = np.asarray(config.get('image_points'),dtype=np.float32)
            road = np.asarray(config.get('road_points'),dtype=np.float32)
            if image.shape != (4,2) or road.shape != (4,2) or not np.isfinite(image).all() or not np.isfinite(road).all():
                raise ValueError('Calibration needs four finite image and road-plane points.')
            for points in (image,road):
                if not cv2.isContourConvex(points) or abs(cv2.contourArea(points)) < 1e-5:
                    raise ValueError('Use four distinct, convex, ordered calibration points.')
            self.matrix = cv2.getPerspectiveTransform(image,road)
            if not np.isfinite(self.matrix).all() or abs(np.linalg.det(self.matrix)) < 1e-10:
                raise ValueError('Degenerate calibration.')
            self.units = 'normalized road units'
        for corridor in self.corridors:
            polygon = np.asarray(corridor.get('polygon'),dtype=np.float32)
            if polygon.ndim != 2 or polygon.shape[1:] != (2,) or len(polygon)<3 or not np.isfinite(polygon).all():
                raise ValueError('Each corridor needs a finite polygon of at least three points.')
            if corridor.get('movement') not in ('STRAIGHT','LEFT TURN','RIGHT TURN','MERGE'):
                raise ValueError('Choose STRAIGHT, LEFT TURN, RIGHT TURN or MERGE.')

    def project(self, point):
        if self.matrix is None: return None
        homogeneous = self.matrix@np.array([*point,1.])
        if abs(homogeneous[2])<1e-6: return None
        return (homogeneous[:2]/homogeneous[2]).tolist()

    def corridor(self, point):
        for region in self.corridors:
            polygon = np.asarray(region['polygon'],dtype=np.float32)
            if cv2.pointPolygonTest(polygon,tuple(map(float,point)),False)>=0:
                return region['movement']
        return None
