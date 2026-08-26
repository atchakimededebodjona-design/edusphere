const { getDefaultConfig } = require("expo/metro-config");
const path = require("path");

// pnpm installe node_modules via des symlinks vers un store partagé (.pnpm) à la racine du
// monorepo — le résolveur Metro par défaut ne les suit pas et ne surveille que ce dossier de
// l'app, ce qui casse la résolution de tout paquet ici (ex. expo-router/entry). Config
// monorepo documentée par Expo : https://docs.expo.dev/guides/monorepos/
const projectRoot = __dirname;
const workspaceRoot = path.resolve(projectRoot, "../..");
const workspaceNodeModules = path.resolve(workspaceRoot, "node_modules");

const config = getDefaultConfig(projectRoot);

// Surveiller uniquement node_modules à la racine (où vit le store .pnpm), pas tout le
// monorepo : watchFolders=[workspaceRoot] laissait Metro voir aussi apps/web (et son propre
// react@18.3.1, différent de react@18.2.0 ici), ce qui produisait deux copies de React vues
// comme des modules Haste distincts — plantage "Invalid hook call" / useId of null dès qu'un
// composant utilisant des hooks se rendait (ex. l'overlay d'erreur de @expo/metro-runtime).
config.watchFolders = [workspaceNodeModules];
config.resolver.nodeModulesPaths = [path.resolve(projectRoot, "node_modules"), workspaceNodeModules];
// PAS de disableHierarchicalLookup ici : ce réglage (recommandé pour les monorepos Yarn/npm à
// node_modules aplati) casse la résolution avec pnpm, dont chaque paquet garde ses propres
// dépendances directes dans son propre node_modules imbriqué (ex. expo-modules-core à côté de
// expo dans le store .pnpm) — la remontée hiérarchique doit rester active pour les trouver.
config.resolver.unstable_enableSymlinks = true;

module.exports = config;
