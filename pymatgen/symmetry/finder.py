#!/usr/bin/env python

"""
An interface to the excellent spglib library by Atsushi Togo
(http://spglib.sourceforge.net/) for pymatgen.

v1.0 - Now works with both ordered and disordered structure.

.. note::
    Not all spglib functions are implemented.
"""

from __future__ import division

__author__ = "Shyue Ping Ong"
__copyright__ = "Copyright 2012, The Materials Project"
__version__ = "1.0"
__maintainer__ = "Shyue Ping Ong"
__email__ = "shyue@mit.edu"
__date__ = "Mar 9, 2012"

import re
import itertools

import numpy as np
import math
from math import cos
from math import sin

from pymatgen.core.structure import Structure
from pymatgen.symmetry.spacegroup import Spacegroup
from pymatgen.symmetry.structure import SymmetrizedStructure
from pymatgen.core.operations import SymmOp
from pymatgen.core.lattice import Lattice
from pymatgen.core.structure import PeriodicSite
from pymatgen.core.structure_modifier import SupercellMaker

try:
    import pymatgen._spglib as spg
except ImportError:
    try:
        import pyspglib._spglib as spg
    except ImportError:
        msg = "Spglib required. Please either run python setup.py install" + \
              " for pymatgen, or install pyspglib from spglib."
        raise ImportError(msg)

tol = 1e-5


class SymmetryFinder(object):
    """
    Takes a pymatgen.core.structure.Structure object and a symprec.
    Uses pyspglib to perform various symmetry finding operations.
    """

    def __init__(self, structure, symprec=1e-5, angle_tolerance=5):
        """
        Args:
            structure:
                Structure object
            symprec:
                Tolerance for symmetry finding
            angle_tolerance:
                Angle tolerance for symmetry finding.
        """
        self._symprec = symprec
        self._angle_tol = angle_tolerance
        self._structure = structure

        #Spglib"s convention for the lattice definition is the transpose of the
        #pymatgen version.
        self._transposed_latt = structure.lattice.matrix.transpose()
        #Spglib requires numpy floats.
        self._transposed_latt = self._transposed_latt.astype(float)
        self._positions = np.array([site.frac_coords for site in structure])
        unique_species = []
        zs = []

        for species, g in itertools.groupby(structure,
                                            key=lambda s: s.species_and_occu):
            try:
                ind = unique_species.index(species)
                zs.extend([ind + 1] * len(tuple(g)))
            except ValueError:
                unique_species.append(species)
                zs.extend([len(unique_species)] * len(tuple(g)))
        self._unique_species = unique_species
        self._numbers = np.array(zs)
        self._spacegroup_data = spg.spacegroup(self._transposed_latt.copy(),
                                               self._positions.copy(),
                                               self._numbers, self._symprec,
                                               self._angle_tol)

    def get_spacegroup(self):
        """
        Return space group in international table symbol and number
        as a string.
        """
        # Atomic positions have to be specified by scaled positions for spglib.
        return Spacegroup(self.get_spacegroup_symbol(),
                          self.get_spacegroup_number(),
                          self.get_symmetry_operations())

    def get_spacegroup_symbol(self):
        """
        Get the spacegroup symbol (e.g., Pnma) for structure.

        Returns:
            Spacegroup symbol for structure.
        """
        return self._spacegroup_data.split()[0]

    def get_spacegroup_number(self):
        """
        Get the international spacegroup number (e.g., 62) for structure.

        Returns:
            International spacegroup number for structure.
        """
        sgnum = self._spacegroup_data.split()[-1]
        sgnum = int(re.sub("\D", "", sgnum))
        return sgnum

    def get_hall(self):
        """
        Returns Hall symbol for structure.
        """
        ds = self.get_symmetry_dataset()
        return ds["hall"]

    def get_point_group(self):
        """
        Get the point group associated with the structure.

        Returns:
            Pointgroup for structure.
        """
        ds = self.get_symmetry_dataset()
        return get_point_group(ds["rotations"])[0].strip()

    def get_crystal_system(self):
        """
        Get the crystal system for the structure, e.g., (triclinic,
        orthorhombic, cubic, etc.).

        Returns:
            Crystal system for structure.
        """
        n = self.get_spacegroup_number()

        f = lambda i, j: i <= n <= j
        cs = {"triclinic": (1, 2), "monoclinic": (3, 15),
              "orthorhombic": (16, 74), "tetragonal": (75, 142),
              "trigonal": (143, 167), "hexagonal": (168, 194),
              "cubic": (195, 230)}

        crystal_sytem = None

        for k, v in cs.items():
            if f(*v):
                crystal_sytem = k
                break
        return crystal_sytem

    def get_lattice_type(self):
        """
        Get the lattice for the structure, e.g., (triclinic,
        orthorhombic, cubic, etc.).This is the same than the
        crystal system with the exception of the hexagonal/rhombohedral
        lattice

        Returns:
            Crystal system for structure.
        """
        n = self.get_spacegroup_number()
        system = self.get_crystal_system()
        if n in [146, 148, 155, 160, 161, 166, 167]:
            return "rhombohedral"
        elif system == "trigonal":
            return "hexagonal"
        else:
            return system

    def get_symmetry_dataset(self):
        """
        Returns the symmetry dataset as a dict.

        Returns:
            number:
                International space group number
            international:
                International symbol
            hall:
                Hall symbol
            transformation_matrix:
                Transformation matrix from lattice of input cell to Bravais
                lattice
                L^bravais = L^original * Tmat
            origin shift:
                Origin shift in the setting of "Bravais lattice"
            rotations, translations:
                Rotation matrices and translation vectors.
                Space group operations are obtained by
                [(r,t) for r, t in zip(rotations, translations)]
            wyckoffs:
                  Wyckoff letters
        """
        keys = ("number",
                "international",
                "hall",
                "transformation_matrix",
                "origin_shift",
                "rotations",
                "translations",
                "wyckoffs",
                "equivalent_atoms")
        dataset = {}
        for key, data in zip(keys, spg.dataset(self._transposed_latt.copy(),
                                               self._positions, self._numbers,
                                               self._symprec,
                                               self._angle_tol)):
            dataset[key] = data
        dataset["international"] = dataset["international"].strip()
        dataset["hall"] = dataset["hall"].strip()
        dataset["transformation_matrix"] = \
            np.array(dataset["transformation_matrix"])
        dataset["origin_shift"] = np.array(dataset["origin_shift"])
        dataset["rotations"] = np.array(dataset["rotations"])
        dataset["translations"] = np.array(dataset["translations"])
        letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        dataset["wyckoffs"] = [letters[x] for x in dataset["wyckoffs"]]
        dataset["equivalent_atoms"] = np.array(dataset["equivalent_atoms"])

        return dataset

    def _get_symmetry(self):
        """
        Get the symmetry operations associated with the structure.

        Returns:
            Symmetry operations as a tuple of two equal length sequences.
            (rotations, translations). "rotations" is the numpy integer array
            of the rotation matrices for scaled positions
            "translations" gives the numpy float64 array of the translation
            vectors in scaled positions.
        """

        # Get number of symmetry operations and allocate symmetry operations
        # multi = spg.multiplicity(cell, positions, numbers, symprec)
        multi = 48 * self._structure.num_sites
        rotation = np.zeros((multi, 3, 3), dtype=int)
        translation = np.zeros((multi, 3))

        num_sym = spg.symmetry(rotation, translation,
                               self._transposed_latt.copy(),
                               self._positions, self._numbers, self._symprec,
                               self._angle_tol)
        return rotation[:num_sym], translation[:num_sym]

    def get_symmetry_operations(self, cartesian=False):
        """
        Return symmetry operations as a list of SymmOp objects.
        By default returns fractional coord symmops.
        But cartesian can be returned too.
        """
        (rotation, translation) = self._get_symmetry()
        symmops = []
        mat = self._structure.lattice.matrix.T
        invmat = np.linalg.inv(mat)
        for rot, trans in zip(rotation, translation):
            if cartesian:
                rot = np.dot(mat, np.dot(rot, invmat))
                trans = np.dot(trans, self._structure.lattice.matrix)
            op = SymmOp.from_rotation_and_translation(rot, trans)
            symmops.append(op)
        return symmops

    def get_symmetrized_structure(self):
        """
        Get a symmetrized structure. A symmetrized structure is one where the
        sites have been grouped into symmetrically equivalent groups.

        Returns:
            pymatgen.symmetry.structure.SymmetrizedStructure object.
        """
        ds = self.get_symmetry_dataset()
        sg = Spacegroup(self.get_spacegroup_symbol(),
                        self.get_spacegroup_number(),
                        self.get_symmetry_operations())
        return SymmetrizedStructure(self._structure, sg,
                                    ds["equivalent_atoms"])

    def get_refined_structure(self):
        """
        Get the refined structure based on detected symmetry. The refined
        structure is a *conventional* cell setting with atoms moved to the
        expected symmetry positions.

        Returns:
            Refined structure.
        """
        # Atomic positions have to be specified by scaled positions for spglib.
        num_atom = self._structure.num_sites
        lattice = self._transposed_latt.copy()
        pos = np.zeros((num_atom * 4, 3), dtype=float)
        pos[:num_atom] = self._positions.copy()

        numbers = np.zeros(num_atom * 4, dtype=int)
        numbers[:num_atom] = self._numbers.copy()
        num_atom_bravais = spg.refine_cell(lattice,
                                           pos,
                                           numbers,
                                           num_atom,
                                           self._symprec,
                                           self._angle_tol)
        zs = numbers[:num_atom_bravais]
        species = [self._unique_species[i - 1] for i in zs]
        s = Structure(lattice.T.copy(), species, pos[:num_atom_bravais])
        return s.get_sorted_structure()

    def find_primitive(self):
        """
        Find a primitive version of the unit cell.

        Returns:
            A primitive cell in the input cell is searched and returned
            as an Structure object. If no primitive cell is found, None is
            returned.
        """

        # Atomic positions have to be specified by scaled positions for spglib.
        positions = self._positions.copy()
        lattice = self._transposed_latt.copy()
        numbers = self._numbers.copy()
        # lattice is transposed with respect to the definition of Atoms class
        num_atom_prim = spg.primitive(lattice, positions, numbers,
                                      self._symprec, self._angle_tol)
        zs = numbers[:num_atom_prim]
        species = [self._unique_species[i - 1] for i in zs]

        if num_atom_prim > 0:
            return Structure(lattice.T, species, positions[:num_atom_prim])
        else:
            #Not sure if we should return None or just return the full
            #structure.
            return self._structure

    def get_ir_kpoints_mapping(self, kpoints, is_time_reversal=True):
        """
        Irreducible k-points are searched from the input kpoints. The result is
        returned as a map of numbers. The array index of map corresponds to the
        reducible k-point numbering. After finding irreducible k-points, the
        indices of the irreducible k-points are mapped to the elements of map,
        i.e., number of unique values in map is the number of the irreducible
        k-points.

        Args:
            kpoints:
                Input kpoints as a (Nx3) array.
            is_time_reversal:
                Set to True to impose time reversal symmetry.

        Returns:
            Numbering of reducible kpoints. Equivalent kpoints will have the
            same number. The number of unique values is the number of the
            irreducible kpoints.
        """
        npkpoints = np.array(kpoints)
        mapping = np.zeros(npkpoints.shape[0], dtype=int)
        positions = self._positions.copy()
        lattice = self._transposed_latt.copy()
        numbers = self._numbers.copy()
        spg.ir_kpoints(mapping, npkpoints, lattice, positions, numbers,
                       is_time_reversal * 1, self._symprec)
        return mapping

    def get_ir_kpoints(self, kpoints, is_time_reversal=True):
        """
        Irreducible k-points are searched from the input kpoints.

        Args:
            kpoints:
                Input kpoints as a (Nx3) array.
            is_time_reversal:
                Set to True to impose time reversal symmetry.

        Returns:
            A set of irreducible kpoints.
        """
        mapping = self.get_ir_kpoints_mapping(kpoints, is_time_reversal)
        irr_kpts = []
        n = []
        for i, kpts in enumerate(kpoints):
            if mapping[i] not in n:
                irr_kpts.append(kpts)
                n.append(i)
        return irr_kpts

    def get_primitive_standard_structure(self):
        """
        Gives a structure with a primitive cell according to certain standards
        the standards are defined in Setyawan, W., & Curtarolo, S. (2010).
        High-throughput electronic band structure calculations:
        Challenges and tools. Computational Materials Science,
        49(2), 299-312. doi:10.1016/j.commatsci.2010.05.010

        Returns:
            The structure in a primitive standardized cell
        """
        conv = self.get_conventional_standard_structure()
        lattice = self.get_lattice_type()

        if "P" in self.get_spacegroup_symbol() or lattice == "hexagonal":
            return conv

        if lattice == "rhombohedral":
            conv = self.get_refined_structure()
            lengths, angles = conv.lattice.lengths_and_angles
            a = lengths[0]
            alpha = math.pi * angles[0] / 180
            new_matrix = [
                [a * cos(alpha / 2), -a * sin(alpha / 2), 0],
                [a * cos(alpha / 2), a * sin(alpha / 2), 0],
                [a * cos(alpha) / cos(alpha / 2), 0,
                 a * math.sqrt(1 - (cos(alpha) ** 2 / (cos(alpha / 2) ** 2)))]]
            new_sites = []
            for s in conv.sites:
                new_s = PeriodicSite(
                    s.specie, s.frac_coords, Lattice(new_matrix),
                    to_unit_cell=True, properties=s.properties)
                unique = True
                for t in new_sites:
                    if new_s.is_periodic_image(t):
                        unique = False
                if unique:
                    new_sites.append(new_s)
            return Structure.from_sites(new_sites)

        transf = np.eye(3)
        if "I" in self.get_spacegroup_symbol():
            transf = np.array([[-1, 1, 1], [1, -1, 1], [1, 1, -1]],
                              dtype=np.float) / 2
        elif "F" in self.get_spacegroup_symbol():
            transf = np.array([[0, 1, 1], [1, 0, 1], [1, 1, 0]],
                              dtype=np.float) / 2
        elif "C" in self.get_spacegroup_symbol():
            if self.get_crystal_system() == "monoclinic":
                transf = np.array([[1, 1, 0], [-1, 1, 0], [0, 0, 2]],
                                  dtype=np.float) / 2
            else:
                transf = np.array([[1, -1, 0], [1, 1, 0], [0, 0, 2]],
                                  dtype=np.float) / 2
        new_sites = []
        for s in conv.sites:
            new_s = PeriodicSite(
                s.specie, s.coords,
                Lattice(np.dot(transf, conv.lattice.matrix)),
                to_unit_cell=True, coords_are_cartesian=True,
                properties=s.properties)
            unique = True
            for t in new_sites:
                if new_s.is_periodic_image(t):
                    unique = False
            if unique:
                new_sites.append(new_s)
        return Structure.from_sites(new_sites)

    def get_conventional_standard_structure(self):
        """
        Gives a structure with a conventional cell according to certain
        standards. The standards are defined in Setyawan, W., & Curtarolo,
        S. (2010). High-throughput electronic band structure calculations:
        Challenges and tools. Computational Materials Science,
        49(2), 299-312. doi:10.1016/j.commatsci.2010.05.010
        They basically enforce as much as possible
        norm(a1)<norm(a2)<norm(a3)

        Returns:
            The structure in a conventional standardized cell
        """

        struct = self.get_refined_structure()
        lattice = self.get_lattice_type()
        sorted_lengths = sorted(struct.lattice.abc)
        sorted_dic = sorted([{'vec': struct.lattice.matrix[i],
                              'length': struct.lattice.abc[i],
                              'orig_index': i} for i in [0, 1, 2]],
                            key=lambda k: k['length'])
        results = None
        if lattice == "orthorhombic" or lattice == "cubic":
            #you want to keep the c axis where it is
            #to keep the C- settings
            if self.get_spacegroup_symbol().startswith("C"):
                transf = np.zeros(shape=(3, 3))
                transf[2] = [0, 0, 1]
                sorted_lengths = sorted(struct.lattice.abc[:2])
                sorted_dic = sorted([{'vec': struct.lattice.matrix[i],
                                      'length': struct.lattice.abc[i],
                                      'orig_index': i} for i in [0, 1]],
                                    key=lambda k: k['length'])
                for c in range(2):
                    transf[c][sorted_dic[c]['orig_index']] = 1
                    new_matrix = [[sorted_lengths[0], 0, 0],
                                  [0, sorted_lengths[1], 0],
                                  [0, 0, struct.lattice.abc[2]]]
            else:
                transf = np.zeros(shape=(3, 3))
                for c in range(len(sorted_dic)):
                    transf[c][sorted_dic[c]['orig_index']] = 1
                new_matrix = [[sorted_lengths[0], 0, 0],
                              [0, sorted_lengths[1], 0],
                              [0, 0, sorted_lengths[2]]]
            new_sites = []
            for s in struct._sites:
                new_sites.append(
                    PeriodicSite(s.specie, np.dot(transf, s.frac_coords),
                                 Lattice(new_matrix), to_unit_cell=True,
                                 properties=s.properties))
            results = Structure.from_sites(new_sites)

        elif lattice == "tetragonal":
            #find the "a" vectors
            #it is basically the vector repeated two times
            transf = np.zeros(shape=(3, 3))
            a = sorted_lengths[0]
            c = sorted_lengths[2]
            for d in range(len(sorted_dic)):
                transf[d][sorted_dic[d]['orig_index']] = 1

            if abs(sorted_lengths[1] - sorted_lengths[2]) < tol:
                a = sorted_lengths[2]
                c = sorted_lengths[0]
                transf = np.dot([[0, 0, 1], [0, 1, 0], [1, 0, 0]], transf)

            new_matrix = [[a, 0, 0],
                          [0, a, 0],
                          [0, 0, c]]
            new_sites = []
            for s in struct._sites:
                new_sites.append(
                    PeriodicSite(s.specie, np.dot(transf, s.frac_coords),
                                 Lattice(new_matrix), to_unit_cell=True,
                                 properties=s.properties))
            results = Structure.from_sites(new_sites)

        elif lattice == "hexagonal" or lattice == "rhombohedral":
            #for the conventional cell representation,
            #we allways show the rhombohedral lattices as hexagonal

            #check first if we have the refined structure shows a rhombohedral
            #cell
            #if so, make a supercell
            if abs(struct.lattice.abc[0] - struct.lattice.abc[1]) < 0.001 and \
                    abs(struct.lattice.abc[2]
                        - struct.lattice.abc[1]) < 0.001 \
                    and abs(struct.lattice.abc[0]
                            - struct.lattice.abc[2]) < 0.001:
                struct = SupercellMaker(struct, ((1, -1, 0), (0, 1, -1),
                                                 (1, 1, 1))).modified_structure
                sorted_lengths = sorted(struct.lattice.abc)

            a = sorted_lengths[0]
            c = sorted_lengths[2]

            if abs(sorted_lengths[1] - sorted_lengths[2]) < 0.001:
                a = sorted_lengths[2]
                c = sorted_lengths[0]
            new_matrix = [[a / 2, -a * math.sqrt(3) / 2, 0],
                          [a / 2, a * math.sqrt(3) / 2, 0],
                          [0, 0, c]]

            new_sites = []
            for s in struct._sites:
                new_sites.append(
                    PeriodicSite(s.specie, s.coords, Lattice(new_matrix),
                                 to_unit_cell=True, coords_are_cartesian=True,
                                 properties=s.properties))
            results = Structure.from_sites(new_sites)

        elif lattice == "monoclinic":
            #you want to keep the c axis where it is
            #to keep the C- settings

            if self.get_spacegroup().int_symbol.startswith("C"):
                trans = np.zeros(shape=(3, 3))
                trans[2] = [0, 0, 1]
                sorted_dic = sorted([{'vec': struct.lattice.matrix[i],
                                      'length': struct.lattice.abc[i],
                                      'orig_index': i} for i in [0, 1]],
                                    key=lambda k: k['length'])
                a = sorted_dic[0]['length']
                b = sorted_dic[1]['length']
                c = struct.lattice.abc[2]
                new_matrix = None
                for t in itertools.permutations(range(2), 2):
                    landang = Lattice([struct.lattice.matrix[t[0]],
                                       struct.lattice.matrix[t[1]],
                                       struct.lattice.matrix[2]]) \
                        .lengths_and_angles
                    if landang[1][0] > 90:
                        #if the angle is > 90 we invert a and b to get
                        #an angle < 90
                        landang = Lattice(
                            [np.multiply(struct.lattice.matrix[t[0]], -1),
                             np.multiply(struct.lattice.matrix[t[1]], -1),
                             struct.lattice.matrix[2]]).lengths_and_angles
                        trans = np.zeros(shape=(3, 3))
                        trans[0][t[0]] = -1
                        trans[1][t[1]] = -1
                        trans[2][2] = 1
                        a = landang[0][0]
                        b = landang[0][1]
                        c = landang[0][2]
                        alpha = math.pi * landang[1][0] / 180
                        new_matrix = [[a, 0, 0],
                                      [0, b, 0],
                                      [0, c * cos(alpha), c * sin(alpha)]]
                        continue

                    elif landang[1][0] < 90:
                        landang = Lattice([struct.lattice.matrix[t[0]],
                                           struct.lattice.matrix[t[1]],
                                           struct.lattice.matrix[2]]) \
                            .lengths_and_angles
                        trans = np.zeros(shape=(3, 3))
                        trans[0][t[0]] = 1
                        trans[1][t[1]] = 1
                        trans[2][2] = 1
                        a = landang[0][0]
                        b = landang[0][1]
                        c = landang[0][2]
                        alpha = math.pi * landang[1][0] / 180
                        new_matrix = [[a, 0, 0],
                                      [0, b, 0],
                                      [0, c * cos(alpha), c * sin(alpha)]]
                if new_matrix is None:
                    #this if is to treat the case
                    #where alpha==90 (but we still have a monoclinic sg
                    new_matrix = [[a, 0, 0],
                                  [0, b, 0],
                                  [0, c * cos(alpha), c * sin(alpha)]]
                if new_matrix is None:
                    #this if is to treat the case
                    #where alpha==90 (but we still have a monoclinic sg
                    new_matrix = [[a, 0, 0],
                                  [0, b, 0],
                                  [0, 0, c]]
                    trans = np.zeros(shape=(3, 3))
                    for c in range(len(sorted_dic)):
                        trans[c][sorted_dic[c]['orig_index']] = 1
            #if not C-setting
            else:
                #try all permutations of the axis
                #keep the ones with the non-90 angle=alpha
                #and b<c
                new_matrix = None
                for t in itertools.permutations(range(3), 3):
                    landang = Lattice([struct.lattice.matrix[t[0]],
                                       struct.lattice.matrix[t[1]],
                                       struct.lattice.matrix[t[2]]]) \
                        .lengths_and_angles
                    if landang[1][0] > 90 and landang[0][1] < landang[0][2]:
                        landang = Lattice(
                            [np.multiply(struct.lattice.matrix[t[0]], -1.0),
                             np.multiply(struct.lattice.matrix[t[1]], -1.0),
                             struct.lattice.matrix[t[2]]]).lengths_and_angles
                        trans = np.zeros(shape=(3, 3))
                        trans[0][t[0]] = -1
                        trans[1][t[1]] = -1
                        trans[2][t[2]] = 1
                        a = landang[0][0]
                        b = landang[0][1]
                        c = landang[0][2]
                        alpha = math.pi * landang[1][0] / 180
                        new_matrix = [[a, 0, 0],
                                      [0, b, 0],
                                      [0, c * cos(alpha), c * sin(alpha)]]
                        continue
                    elif landang[1][0] < 90 and landang[0][1] < landang[0][2]:
                        landang = Lattice([struct.lattice.matrix[t[0]],
                                           struct.lattice.matrix[t[1]],
                                           struct.lattice.matrix[t[2]]]) \
                            .lengths_and_angles
                        trans = np.zeros(shape=(3, 3))
                        trans[0][t[0]] = 1
                        trans[1][t[1]] = 1
                        trans[2][t[2]] = 1
                        a = landang[0][0]
                        b = landang[0][1]
                        c = landang[0][2]
                        alpha = math.pi * landang[1][0] / 180
                        new_matrix = [[a, 0, 0],
                                      [0, b, 0],
                                      [0, c * cos(alpha), c * sin(alpha)]]
                if new_matrix is None:
                    trans = np.zeros(shape=(3, 3))
                    for c in range(len(sorted_dic)):
                        trans[c][sorted_dic[c]['orig_index']] = 1

            new_sites = []
            for s in struct._sites:
                new_sites.append(
                    PeriodicSite(s.specie, np.dot(trans, s.frac_coords),
                                 Lattice(new_matrix), to_unit_cell=True,
                                 properties=s.properties))
            results = Structure.from_sites(new_sites)

        elif lattice == "triclinic":
            #we use a LLL Minkowski-like reduction for the triclinic cells
            struct = struct.get_reduced_structure("LLL")

            a = struct.lattice.lengths_and_angles[0][0]
            b = struct.lattice.lengths_and_angles[0][1]
            c = struct.lattice.lengths_and_angles[0][2]
            alpha = math.pi * struct.lattice.lengths_and_angles[1][0] / 180
            beta = math.pi * struct.lattice.lengths_and_angles[1][1] / 180
            gamma = math.pi * struct.lattice.lengths_and_angles[1][2] / 180
            new_matrix = [[a, 0, 0],
                          [b * cos(gamma), b * sin(gamma), 0.0],
                          [c * cos(beta),
                           c * (cos(alpha) - cos(beta) * cos(gamma)) /
                           sin(gamma),
                           c * math.sqrt(sin(gamma) ** 2 - cos(alpha) ** 2
                                         - cos(beta) ** 2
                                         + 2 * cos(alpha) * cos(beta)
                                         * cos(gamma)) / sin(gamma)]]
            new_sites = []
            for s in struct._sites:
                new_sites.append(
                    PeriodicSite(s.specie, s.frac_coords, Lattice(new_matrix),
                                 to_unit_cell=False, properties=s.properties))
            results = Structure.from_sites(new_sites)

        return results.get_sorted_structure()


def get_point_group(rotations):
    """
    Return point group in international table symbol and number.
    The symbols are mapped to the numbers as follows:
    1   "1    "
    2   "-1   "
    3   "2    "
    4   "m    "
    5   "2/m  "
    6   "222  "
    7   "mm2  "
    8   "mmm  "
    9   "4    "
    10  "-4   "
    11  "4/m  "
    12  "422  "
    13  "4mm  "
    14  "-42m "
    15  "4/mmm"
    16  "3    "
    17  "-3   "
    18  "32   "
    19  "3m   "
    20  "-3m  "
    21  "6    "
    22  "-6   "
    23  "6/m  "
    24  "622  "
    25  "6mm  "
    26  "-62m "
    27  "6/mmm"
    28  "23   "
    29  "m-3  "
    30  "432  "
    31  "-43m "
    32  "m-3m "
    """
    if rotations.dtype == "float64":
        rotations = np.int_(rotations)
        # (symbol, pointgroup_number, transformation_matrix)
    return spg.pointgroup(rotations)
