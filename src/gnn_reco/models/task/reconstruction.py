import numpy as np
import torch

from gnn_reco.models.task import Task
from gnn_reco.utils import eps_like




class TrackCascadeClassification(Task):
    # Requires two features: untransformed points in (x,y)-space.
    nb_inputs = 1

    def _forward(self, x):
        return x

class NeutrinoNotNeutrionoClassification(Task):
    # Requires two features: untransformed points in (x,y)-space.
    nb_inputs = 1

    def _forward(self, x):
        return x

class AzimuthReconstructionWithKappa(Task):
    """Reconstructs azimuthal angle and associated kappa (1/var)."""
    # Requires two features: untransformed points in (x,y)-space.
    nb_inputs = 2

    def _forward(self, x):
        # Transform outputs to angle and prepare prediction
        kappa = torch.linalg.vector_norm(x, dim=1) + eps_like(x)
        angle = torch.atan2(x[:,1], x[:,0])
        angle = torch.where(angle < 0, angle + 2 * np.pi, angle)  # atan(y,x) -> [-pi, pi]
        return torch.stack((angle, kappa), dim=1)

class XYZReconstruction(Task):
    # Requires two features: untransformed points in (x,y)-space.
    nb_inputs = 3

    def _forward(self, x):
        # Transform outputs
        #x[:,0] = x[:,0]*100
        #x[:,1] = x[:,1]*100
        #x[:,2] = x[:,2]*100
        #x[:,3] = x[:,3]*9000 
        return x

class TReconstruction(Task):
    # Requires two features: untransformed points in (x,y)-space.
    nb_inputs = 1

    def _forward(self, x):
        # Transform outputs
        #x[:,0] = x[:,0]*100
        #x[:,1] = x[:,1]*100
        #x[:,2] = x[:,2]*100
        #x[:,3] = x[:,3]*9000 
        return x

class AzimuthReconstruction(AzimuthReconstructionWithKappa):
    """Reconstructs azimuthal angle."""
    # Requires two features: untransformed points in (x,y)-space.
    nb_inputs = 2

    def _forward(self, x):
        # Transform outputs to angle and prepare prediction
        res = super()._forward(x)
        angle = res[:,0].unsqueeze(1)
        kappa = res[:,1]
        sigma = torch.sqrt(1. / kappa)
        beta = 1e-3
        kl_loss = torch.mean(sigma**2 - torch.log(sigma) - 1)
        self._regularisation_loss += beta * kl_loss
        return angle


class ZenithReconstruction(Task):
    """Reconstructs zenith angle."""
    # Requires two features: untransformed points in (x,y)-space.
    nb_inputs = 1

    def _forward(self, x):
        # Transform outputs to angle and prepare prediction
        return torch.sigmoid(x[:,:1]) * np.pi

class ZenithReconstructionWithKappa(ZenithReconstruction):
    """Reconstructs zenith angle and associated kappa (1/var)."""
    # Requires one feature in addition to `ZenithReconstruction`: kappa (unceratinty; 1/variance).
    nb_inputs = 2

    def _forward(self, x):
        # Transform outputs to angle and prepare prediction
        angle = super()._forward(x[:,:1]).squeeze(1)
        kappa = torch.abs(x[:,1]) + eps_like(x)
        return torch.stack((angle, kappa), dim=1)


class EnergyReconstruction(Task):
    """Reconstructs energy."""
    # Requires one feature: untransformed energy
    nb_inputs = 1

    def _forward(self, x):
        # Transform energy
        return x[:,0].unsqueeze(1) #torch.pow(10, x[:,0] + 1.).unsqueeze(1)

class EnergyReconstructionWithUncertainty(EnergyReconstruction):
    """Reconstructs energy and associated uncertainty (log(var))."""
    # Requires one feature in addition to `EnergyReconstruction`: log-variance (uncertainty).
    nb_inputs = 2

    def _forward(self, x):
        # Transform energy
        energy = super()._forward(x[:,:1]).squeeze(1)
        log_var = x[:,1]
        pred = torch.stack((energy, log_var), dim=1)
        return pred
