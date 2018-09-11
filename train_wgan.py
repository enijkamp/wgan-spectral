import argparse
import logging
import sys
import os
import datetime

import numpy as np

import torch
import torch.nn as nn
from torch.nn.utils.spectral_norm import spectral_norm
import torch.nn.functional as F

from torchvision import datasets, transforms
import torchvision.utils as vutils

import inception_score_v3 as is_v3


class Generator(torch.nn.Module):
    def __init__(self, nz=128, nc=3, ngf=512):
        super(Generator, self).__init__()

        self.nz = nz
        self.ngf = ngf

        self.l0_0 = torch.nn.Linear(nz, 4 * 4 * ngf)
        self.l0_1 = torch.nn.BatchNorm2d(4 * 4 * ngf)
        self.l0_2 = torch.nn.ReLU(inplace=True)

        self.dc1_0 = torch.nn.ConvTranspose2d(ngf, ngf // 2, 4, 2, 1)
        self.dc1_1 = torch.nn.BatchNorm2d(ngf // 2)
        self.dc1_2 = torch.nn.ReLU(inplace=True)

        self.dc2_0 = torch.nn.ConvTranspose2d(ngf // 2, ngf // 4, 4, 2, 1)
        self.dc2_1 = torch.nn.BatchNorm2d(ngf // 4)
        self.dc2_2 = torch.nn.ReLU(inplace=True)

        self.dc3_0 = torch.nn.ConvTranspose2d(ngf // 4, ngf // 8, 4, 2, 1)
        self.dc3_1 = torch.nn.BatchNorm2d(ngf // 8)
        self.dc3_2 = torch.nn.ReLU(inplace=True)

        self.dc4_0 = torch.nn.ConvTranspose2d(ngf // 8, nc, 3, 1, 1)
        self.dc4_1 = torch.nn.Tanh()

    def forward(self, z):
        l0 = self.l0_2(self.l0_1(self.l0_0(z)))
        l0 = l0.view(self.nz, self.ngf, 4, 4)
        dc1 = self.dc1_2(self.dc1_1(self.dc1_0(l0)))
        dc2 = self.dc2_2(self.dc2_1(self.dc2_0(dc1)))
        dc3 = self.dc3_2(self.dc3_1(self.dc3_0(dc2)))
        dc4 = self.dc4_2(self.dc4_1(self.dc4_0(dc3)))

        return dc4


class Generator(torch.nn.Module):
    def __init__(self, nz=128, nc=3, ngf=512):
        super().__init__()

        self.nz = nz
        self.ngf = ngf

        self.linear = nn.Linear(nz, 4 * 4 * ngf)
        self.activation = nn.ReLU()
        self.deconv = nn.Sequential(
            nn.ConvTranspose2d(self.ngf, self.ngf // 2, 4, 2, 1),
            nn.BatchNorm2d(self.ngf // 2),
            nn.ReLU(),

            nn.ConvTranspose2d(self.ngf // 2, self.ngf // 4, 4, 2, 1),
            nn.BatchNorm2d(self.ngf // 4),
            nn.ReLU(),

            nn.ConvTranspose2d(self.ngf // 4, self.ngf // 8, 4, 2, 1),
            nn.BatchNorm2d(self.ngf // 8),
            nn.ReLU(),

            nn.ConvTranspose2d(self.ngf // 8, nc, nc, 1, 1),
            nn.Tanh()
        )

    def forward(self, z):
        out = self.activation(self.linear(z))
        out = out.view(-1, self.ngf, 4, 4)
        out = self.deconv(out)

        return out


class Discriminator(torch.nn.Module):
    def __init__(self, ndf=512, nc=3):
        super().__init__()

        self.layer1 = self.layer(3, ndf // 8)
        self.layer2 = self.layer(ndf // 8, ndf // 4)
        self.layer3 = self.layer(ndf // 4, ndf // 2)
        self.layer4 = spectral_norm(nn.Conv2d(ndf // 2, ndf, nc, 1, 1))
        self.linear = spectral_norm(nn.Linear(ndf * 4 * 4, 1))

    def layer(self, in_plane, out_plane):
        return torch.nn.Sequential(
            spectral_norm(nn.Conv2d(in_plane, out_plane, 3, 1, 1)),
            nn.LeakyReLU(0.1),
            spectral_norm(nn.Conv2d(out_plane, out_plane, 4, 2, 1)),
            nn.LeakyReLU(0.1)
        )

    def forward(self, x):
        out = self.layer1(x)
        out = self.layer2(out)
        out = self.layer3(out)
        out = self.layer4(out)
        out = out.view(out.size(0), -1)
        out = self.linear(out)

        return out.squeeze()


def get_exp_id():
    return os.path.splitext(os.path.basename(__file__))[0]


def get_output_dir(exp_id):
    t = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    output_dir = os.path.join('output/' + exp_id, t)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    return output_dir


def create_logger(output_dir, console=True):
    log_format = logging.Formatter("%(asctime)s : %(message)s")
    logger = logging.getLogger('')
    logger.handlers = []
    output_file = os.path.join(output_dir, 'output.log')
    file_handler = logging.FileHandler(output_file)
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(log_format)
        logger.addHandler(console_handler)
    logger.setLevel(logging.INFO)
    return logger


output_dir = get_output_dir(get_exp_id())
logger = create_logger(output_dir)

parser = argparse.ArgumentParser()
parser.add_argument('--batch_size', type=int, default=64)
parser.add_argument('--lr', type=float, default=0.0001)
parser.add_argument('--nz', type=int, default=128)

args = parser.parse_args()

loader = torch.utils.data.DataLoader(
    datasets.CIFAR10('data', train=True, download=True,
                     transform=transforms.Compose([
                         transforms.Resize(32),
                         transforms.ToTensor(),
                         transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))])),
    batch_size=args.batch_size, shuffle=True, num_workers=1, pin_memory=True)

net_d = Discriminator().cuda()
net_g = Generator(nz=args.nz).cuda()

logger.info(args)
logger.info(net_d)
logger.info(net_g)

train_flag = lambda: [net.train() for net in [net_d, net_g]]
eval_flag = lambda: [net.eval() for net in [net_d, net_g]]
grad_norm = lambda net: torch.sqrt(sum(torch.sum(p.grad**2) for p in net.parameters() if p.grad is not None))

def weights_init(m):
    classname = m.__class__.__name__
    if classname.find('Conv') != -1:
        m.weight.data.normal_(0.0, 0.02)
    elif classname.find('BatchNorm') != -1:
        m.weight.data.normal_(1.0, 0.02)
        m.bias.data.fill_(0)

net_d.apply(weights_init)
net_g.apply(weights_init)

optim_d = torch.optim.Adam(net_d.parameters(), lr=args.lr, betas=(0.5, 0.999))
optim_g = torch.optim.Adam(net_g.parameters(), lr=args.lr, betas=(0.5, 0.999))

logger.info(('{:>14}'*8).format('epoch', 'E(real)', 'E(fake)', 'loss(D)', 'loss(G)', 'grad(D)', 'grad(G)', 'incept_v3'))

z_fixed = torch.tensor(torch.randn(64, args.nz)).cuda()

for epoch in range(200):
    loss_d_s, loss_g_s, grad_d_s, grad_g_s, e_real_s, e_fake_s = [], [], [], [], [], []

    train_flag()
    for i, (x, _) in enumerate(loader):
        net_d.zero_grad()

        z = torch.randn(args.batch_size, args.nz).cuda()
        x_hat = net_g(z).detach()
        x = x.cuda()

        e_real = F.softplus(-net_d(x).mean())
        e_fake = F.softplus(net_d(x_hat).mean())
        loss_d = e_real + e_fake
        loss_d.backward()
        optim_d.step()

        net_g.zero_grad()
        loss_g = -net_d(net_g(z)).mean()
        loss_g.backward()
        optim_g.step()

        loss_d_s.append(loss_d.data.item())
        loss_g_s.append(loss_g.data.item())
        grad_d_s.append(grad_norm(net_d).data.item())
        grad_g_s.append(grad_norm(net_g).data.item())
        e_real_s.append(e_real.data.item())
        e_fake_s.append(e_fake.data.item())

    eval_flag()

    num_samples = 1000
    noise_z = torch.FloatTensor(args.batch_size, args.nz)
    new_noise = lambda: noise_z.normal_().cuda()
    gen_samples = torch.cat([net_g(new_noise()).detach().cpu() for _ in range(int(num_samples / 100))])
    incept_v3 = is_v3.inception_score(gen_samples, resize=True, splits=1)[0]

    vutils.save_image(net_g(z_fixed).data, '{}/samples_{}.png'.format(output_dir, epoch), normalize=True)

    logger.info(('{:>14}' + '{:>14.3f}'*7).format(epoch, np.mean(e_real_s), np.mean(e_fake_s), np.mean(loss_d_s), np.mean(loss_g_s), np.mean(grad_d_s), np.mean(grad_g_s), incept_v3))
