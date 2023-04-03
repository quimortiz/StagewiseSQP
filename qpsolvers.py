## This file contains methods to create matrices and solve using prox qp and OSQP for the 
## LQ sub problem 
## Author : Armand Jordana
## Date : 21/03/2022

import numpy as np
import osqp
import proxsuite
import time 
from scipy import sparse
import scipy.linalg as scl
from py_osqp import CustomOSQP


class QPSolvers(CustomOSQP):

    def __init__(self, method):
        
        assert method == "ProxQP" or method=="sparceADMM"  or method=="OSQP" or method=="CustomOSQP" 

        CustomOSQP.__init__(self)
        self.method = method

    def computeDirectionFullQP(self):
        self.calc(True)
        self.n_vars  = self.problem.T*(self.nx + self.nu)

        P = np.zeros((self.problem.T*(self.nx + self.nu), self.problem.T*(self.nx + self.nu)))
        q = np.zeros(self.problem.T*(self.nx + self.nu))
        
        Asize = self.problem.T*(self.nx + self.nu)
        A = np.zeros((self.problem.T*self.nx, Asize))
        B = np.zeros(self.problem.T*self.nx)

        for t, (model, data) in enumerate(zip(self.problem.runningModels, self.problem.runningDatas)):
            if t>=1:
                index_x = (t-1) * self.nx
                P[index_x:index_x+self.nx, index_x:index_x+self.nx] = data.Lxx.copy()
                q[index_x:index_x+self.nx] = data.Lx.copy()

            index_u = self.problem.T*self.nx + t * self.nu
            P[index_u:index_u+self.nu, index_u:index_u+self.nu] = data.Luu.copy()
            q[index_u:index_u+self.nu] = data.Lu.copy()


            
            index_u = self.problem.T*self.nx + t * self.nu
            A[t * self.nx: (t+1) * self.nx, index_u:index_u+self.nu] = - data.Fu 
            A[t * self.nx: (t+1) * self.nx, t * self.nx: (t+1) * self.nx] = np.eye(self.nx)

            if t >=1:
                A[t * self.nx: (t+1) * self.nx, (t-1) * self.nx: t * self.nx] = - data.Fx

            B[t * self.nx: (t+1) * self.nx] = self.gap[t]


        P[self.problem.T*self.nx-self.nx:self.problem.T*self.nx, self.problem.T*self.nx-self.nx:self.problem.T*self.nx] = self.problem.terminalData.Lxx.copy()
        q[self.problem.T*self.nx-self.nx:self.problem.T*self.nx] = self.problem.terminalData.Lx.copy()


        n = self.problem.T*(self.nx + self.nu)
        self.n_eq = self.problem.T*self.nx
        self.n_in = self.problem.T*(self.nx + self.nu)



        C = np.eye(self.n_in)
        l = np.zeros(self.n_in)
        u = np.zeros(self.n_in)

        for t in range(self.problem.T): 
            l[t * self.nx: (t+1) * self.nx] = self.lxmin[t+1] - self.xs[t+1]
            u[t * self.nx: (t+1) * self.nx] = self.lxmax[t+1] - self.xs[t+1] 
            index_u = self.problem.T*self.nx + t * self.nu
            l[index_u: index_u + self.nu] = self.lumin[t] - self.us[t]
            u[index_u: index_u + self.nu] = self.lumax[t] - self.us[t]

        if self.method == "ProxQP":
            qp = proxsuite.proxqp.sparse.QP(n, self.n_eq, self.n_in)
            qp.init(P, q, A, B, C, l, u)      
            t1 = time.time()
            qp.solve()
            print("solve time = ", time.time()-t1)
            res = qp.results.x
            print("n_iter = ", qp.results.info.iter)
            print("n_iter_ext = ", qp.results.info.iter_ext)

        elif self.method == "OSQP":
            Aeq = sparse.csr_matrix(A)
            Aineq = sparse.eye(self.n_in)
            Aosqp = sparse.vstack([Aeq, Aineq])

            losqp = np.hstack([B, l])
            uosqp = np.hstack([B, u])

            P = sparse.csr_matrix(P)
            prob = osqp.OSQP()
            prob.setup(P, q, Aosqp, losqp, uosqp, warm_start=True, scaling=False)     

            t1 = time.time()
            res = prob.solve().x
            print("solve time = ", time.time()-t1)
        # import pdb; pdb.set_trace()

        elif self.method == "CustomOSQP":
            Aeq = sparse.csr_matrix(A)
            Aineq = sparse.eye(self.n_in)
            self.Aosqp = sparse.vstack([Aeq, Aineq])

            self.losqp = np.hstack([B, l])
            self.uosqp = np.hstack([B, u])

            self.P = P
            self.q = np.array(q)
            
            self.xs_vec = np.array(self.xs).flatten()[self.nx:]
            self.us_vec = np.array(self.us).flatten()
            self.xz_vec = np.array(self.xz).flatten()[self.nx:]
            self.uz_vec = np.array(self.uz).flatten()
            self.xy_vec = np.array(self.xy).flatten()[self.nx:]
            self.uy_vec = np.array(self.uy).flatten()
            self.x_k = np.hstack((self.xs_vec, self.us_vec))
            # self.z_k = np.hstack((self.xz_vec, self.uz_vec))
            # self.y_k = np.hstack((self.xy_vec, self.uy_vec))
            self.z_k = np.zeros(self.n_in + self.n_eq)
            self.y_k = np.zeros(self.n_in + self.n_eq)

            ## initializing rho
            self.rho = self.rho_op * np.ones(self.n_eq + self.n_in)
            self.rho[:self.n_eq] *= 1e3
            self.rho_estimate = self.rho_op

            res = self.optimize_osqp(maxiters=1000)


        self.dx[0] = np.zeros(self.nx)
        for t in range(self.problem.T):
            self.dx[t+1] = res[t * self.nx: (t+1) * self.nx] 
            index_u = self.problem.T*self.nx + t * self.nu
            self.du[t] = res[index_u:index_u+self.nu]

        self.x_grad_norm = np.linalg.norm(self.dx)/(self.problem.T+1)
        self.u_grad_norm = np.linalg.norm(self.du)/self.problem.T
