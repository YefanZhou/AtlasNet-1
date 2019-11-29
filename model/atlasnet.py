from __future__ import print_function
import torch
import torch.nn as nn
import torch.nn.parallel
import torch.utils.data
from model.model_blocks import GetDecoder, Identity
from model.template import GetTemplate

class Atlasnet(nn.Module):

    def __init__(self, opt):
        """
        Main Atlasnet module. This network takes an embedding in the form of a latent vector and returns a pointcloud or a mesh
        :param opt: 
        """
        super(Atlasnet, self).__init__()
        self.opt = opt
        self.device = opt.device
        self.nb_pts_in_primitive = opt.number_points // opt.nb_primitives
        if opt.remove_all_batchNorms:
            torch.nn.BatchNorm1d = Identity
            print("Replacing all batchnorms by identities.")

        # Initialize templates
        self.template = [GetTemplate(opt.template_type, device=opt.device) for i in range(0, opt.nb_primitives)]

        # Intialize deformation networks
        self.decoder = nn.ModuleList(
            [GetDecoder(bottleneck_size=opt.bottleneck_size, input_size=opt.dim_template, decoder_type=opt.decoder_type)
             for i in
             range(0, opt.nb_primitives)])

    def forward(self, latent_vector, train=True):
        """
        Deform points from self.template using the embedding latent_vector
        :param latent_vector: an opt.bottleneck size vector encoding a 3D shape or an image.
        :return: A deformed pointcloud
        """
        # Sample points in the patches
        if train:
            input_points = [self.template[i].get_random_points(
                torch.Size((latent_vector.size(0), self.template[i].dim, self.nb_pts_in_primitive))) for i in
                            range(self.opt.nb_primitives)]
        else:
            input_points = [self.template[i].get_regular_points(self.nb_pts_in_primitive).transpose(0, 1).contiguous()
                            for i in range(self.opt.nb_primitives)]
            input_points = [input_points[i].unsqueeze(0).expand(
                torch.Size((latent_vector.size(0), self.template[i].dim, input_points[i].size(1)))) for i in
                            range(self.opt.nb_primitives)]
        # Deform each patch
        output_points = torch.cat([self.decoder[i](input_points[i], latent_vector.unsqueeze(2)).unsqueeze(1) for i in
                                   range(0, self.opt.nb_primitives)], dim=1)

        # Deform return the deformed pointcloud
        return output_points.contiguous()  # batch, nb_prim, num_point, 3

    def generate_mesh(self, latent_vector):
        """
        latent_vector has batch size 1
        :param x:
        :return:
        """
        import pymesh
        input_points = [self.template[i].get_regular_points(self.nb_pts_in_primitive).transpose(0, 1).contiguous()
                        for i in range(self.opt.nb_primitives)]
        input_points = [input_points[i].unsqueeze(0) for i in range(self.opt.nb_primitives)]

        # Deform each patch
        output_points = [self.decoder[i](input_points[i], latent_vector.unsqueeze(2)).squeeze() for i in
                                   range(0, self.opt.nb_primitives)]

        output_meshes = [pymesh.form_mesh(vertices = output_points[i].transpose(1,0).contiguous().cpu().numpy(), faces = self.template[i].mesh.faces)
                         for i in range(self.opt.nb_primitives)]

        # Deform return the deformed pointcloud
        mesh = pymesh.merge_meshes(output_meshes)

        return mesh