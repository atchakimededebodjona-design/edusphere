const { getDefaultConfig } = require("expo/metro-config");
const path = require("path");

// pnpm installe node_modules via des symlinks vers un store partagé (.pnpm) à la racine du
// monorepo — le résolveur Metro par défaut ne les suit pas et ne surveille que ce dossier de
// l'app, ce qui casse la résolution de tout paquet ici (ex. expo-router/entry). Config
// monorepo documentée par Expo : https://docs.expo.dev/guides/monorepos/
const projectRoot = __dirname;
const workspaceRoot = path.resolve(projectRoot, "../..");

const config = getDefaultConfig(projectRoot);

config.watchFolders = [workspaceRoot];
config.resolver.nodeModulesPaths = [
  path.resolve(projectRoot, "node_modules"),
  path.resolve(workspaceRoot, "node_modules"),
];
// PAS de disableHierarchicalLookup ici : ce réglage (recommandé pour les monorepos Yarn/npm à
// node_modules aplati) casse la résolution avec pnpm, dont chaque paquet garde ses propres
// dépendances directes dans son propre node_modules imbriqué (ex. expo-modules-core à côté de
// expo dans le store .pnpm) — la remontée hiérarchique doit rester active pour les trouver.
config.resolver.unstable_enableSymlinks = true;

module.exports = config;
