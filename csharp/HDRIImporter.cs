/*
 * HDRIImporter.cs - Unity Editor Plugin for HDRI Maker
 * 
 * Place this file in your Unity project's Assets/Editor/ folder.
 * It provides an Editor Window for importing .hdr files created by HDRI Maker,
 * converting them to Cubemaps, and applying them as Skybox/Environment lighting.
 * 
 * Usage:
 *   1. Copy this file to Assets/Editor/HDRIImporter.cs in your Unity project
 *   2. Open Window > HDRI Maker > Import HDRI
 *   3. Select your .hdr file and click Import
 * 
 * Compatibility: Unity 2020.3+, Unity 6+
 */

#if UNITY_EDITOR

using UnityEngine;
using UnityEditor;
using System.IO;
using System;

namespace HDRIMaker.Unity
{
    /// <summary>
    /// Unity Editor window for importing HDRI files created by HDRI Maker.
    /// Handles .hdr (Radiance) and .exr (OpenEXR) format files.
    /// </summary>
    public class HDRIImporter : EditorWindow
    {
        // ============================
        //  Private State
        // ============================
        private string _hdriPath = "";
        private Texture2D _previewTexture;
        private Cubemap _generatedCubemap;
        private Material _skyboxMaterial;
        
        // Import settings
        private int _cubemapResolution = 1024;
        private bool _applyAsSkybox = true;
        private bool _updateEnvironmentLighting = true;
        private bool _updateReflections = true;
        private float _exposureOverride = 1.0f;
        private float _rotationOffset = 0.0f;
        private Color _tintColor = Color.white;
        
        // UI state
        private Vector2 _scrollPos;
        private bool _showAdvancedSettings = false;
        private bool _isImporting = false;
        private string _statusMessage = "";
        private MessageType _statusType = MessageType.None;

        // Resolution options
        private readonly int[] _resolutionOptions = { 256, 512, 1024, 2048, 4096 };
        private readonly string[] _resolutionLabels = { "256", "512", "1024", "2048", "4096" };

        // ============================
        //  Menu Item
        // ============================
        [MenuItem("Window/HDRI Maker/Import HDRI", false, 1000)]
        public static void ShowWindow()
        {
            var window = GetWindow<HDRIImporter>("HDRI Maker Importer");
            window.minSize = new Vector2(400, 500);
            window.Show();
        }

        [MenuItem("Window/HDRI Maker/Quick Apply HDRI", false, 1001)]
        public static void QuickApply()
        {
            string path = EditorUtility.OpenFilePanel("Select HDRI File", "", "hdr,exr");
            if (!string.IsNullOrEmpty(path))
            {
                ImportAndApplyHDRI(path, 1024, true, true, true, 1.0f, 0.0f, Color.white);
            }
        }

        // ============================
        //  GUI Drawing
        // ============================
        private void OnGUI()
        {
            _scrollPos = EditorGUILayout.BeginScrollView(_scrollPos);

            DrawHeader();
            DrawFileSelection();
            DrawPreview();
            DrawImportSettings();
            DrawAdvancedSettings();
            DrawImportButton();
            DrawStatusMessage();

            EditorGUILayout.EndScrollView();
        }

        private void DrawHeader()
        {
            EditorGUILayout.Space(10);

            // Title
            var titleStyle = new GUIStyle(EditorStyles.boldLabel)
            {
                fontSize = 18,
                alignment = TextAnchor.MiddleCenter,
                normal = { textColor = new Color(0.3f, 0.7f, 1.0f) }
            };
            EditorGUILayout.LabelField("HDRI Maker Importer", titleStyle, GUILayout.Height(30));

            // Subtitle
            var subtitleStyle = new GUIStyle(EditorStyles.centeredGreyMiniLabel)
            {
                fontSize = 11
            };
            EditorGUILayout.LabelField("Import HDR environment maps into your Unity scene", subtitleStyle);

            EditorGUILayout.Space(10);
            DrawSeparator();
        }

        private void DrawFileSelection()
        {
            EditorGUILayout.Space(5);
            EditorGUILayout.LabelField("HDRI File", EditorStyles.boldLabel);

            EditorGUILayout.BeginHorizontal();
            {
                _hdriPath = EditorGUILayout.TextField(_hdriPath, GUILayout.ExpandWidth(true));

                if (GUILayout.Button("Browse...", GUILayout.Width(80)))
                {
                    string path = EditorUtility.OpenFilePanel(
                        "Select HDRI File",
                        string.IsNullOrEmpty(_hdriPath) ? Application.dataPath : Path.GetDirectoryName(_hdriPath),
                        "hdr,exr,png"
                    );
                    if (!string.IsNullOrEmpty(path))
                    {
                        _hdriPath = path;
                        LoadPreview();
                    }
                }
            }
            EditorGUILayout.EndHorizontal();

            // Drag & drop support
            var dragArea = GUILayoutUtility.GetRect(0, 50, GUILayout.ExpandWidth(true));
            GUI.Box(dragArea, "Drag & Drop HDRI file here", EditorStyles.helpBox);
            HandleDragAndDrop(dragArea);

            EditorGUILayout.Space(5);
        }

        private void DrawPreview()
        {
            if (_previewTexture != null)
            {
                EditorGUILayout.LabelField("Preview", EditorStyles.boldLabel);
                float aspect = (float)_previewTexture.width / _previewTexture.height;
                float previewHeight = Mathf.Min(200, position.width / aspect);
                var previewRect = GUILayoutUtility.GetRect(position.width - 20, previewHeight);
                EditorGUI.DrawPreviewTexture(previewRect, _previewTexture, null, ScaleMode.ScaleToFit);
                
                EditorGUILayout.LabelField(
                    $"Resolution: {_previewTexture.width} x {_previewTexture.height}",
                    EditorStyles.centeredGreyMiniLabel
                );
                EditorGUILayout.Space(5);
            }
        }

        private void DrawImportSettings()
        {
            DrawSeparator();
            EditorGUILayout.LabelField("Import Settings", EditorStyles.boldLabel);

            // Cubemap resolution
            int resIndex = Array.IndexOf(_resolutionOptions, _cubemapResolution);
            if (resIndex < 0) resIndex = 2; // default to 1024
            resIndex = EditorGUILayout.Popup("Cubemap Resolution", resIndex, _resolutionLabels);
            _cubemapResolution = _resolutionOptions[resIndex];

            _applyAsSkybox = EditorGUILayout.Toggle("Apply as Skybox", _applyAsSkybox);
            _updateEnvironmentLighting = EditorGUILayout.Toggle("Update Environment Lighting", _updateEnvironmentLighting);
            _updateReflections = EditorGUILayout.Toggle("Update Reflections", _updateReflections);

            EditorGUILayout.Space(3);
            _exposureOverride = EditorGUILayout.Slider("Exposure", _exposureOverride, 0.1f, 10.0f);
            _rotationOffset = EditorGUILayout.Slider("Rotation", _rotationOffset, 0f, 360f);
            _tintColor = EditorGUILayout.ColorField("Tint", _tintColor);
        }

        private void DrawAdvancedSettings()
        {
            EditorGUILayout.Space(5);
            _showAdvancedSettings = EditorGUILayout.Foldout(_showAdvancedSettings, "Advanced Settings");
            if (_showAdvancedSettings)
            {
                EditorGUI.indentLevel++;
                EditorGUILayout.HelpBox(
                    "For best results:\n" +
                    "• Use 2048 or 4096 cubemap resolution for production\n" +
                    "• Enable 'Update Reflections' for PBR materials\n" +
                    "• Adjust exposure to match your scene's lighting",
                    MessageType.Info
                );
                EditorGUI.indentLevel--;
            }
        }

        private void DrawImportButton()
        {
            EditorGUILayout.Space(10);
            DrawSeparator();
            EditorGUILayout.Space(5);

            EditorGUI.BeginDisabledGroup(_isImporting || string.IsNullOrEmpty(_hdriPath));
            {
                var buttonStyle = new GUIStyle(GUI.skin.button)
                {
                    fontSize = 14,
                    fontStyle = FontStyle.Bold,
                    fixedHeight = 40
                };

                if (GUILayout.Button(_isImporting ? "Importing..." : "Import HDRI", buttonStyle))
                {
                    ImportHDRI();
                }
            }
            EditorGUI.EndDisabledGroup();
        }

        private void DrawStatusMessage()
        {
            if (!string.IsNullOrEmpty(_statusMessage))
            {
                EditorGUILayout.Space(5);
                EditorGUILayout.HelpBox(_statusMessage, _statusType);
            }
        }

        // ============================
        //  Import Logic
        // ============================
        private void ImportHDRI()
        {
            if (!File.Exists(_hdriPath))
            {
                SetStatus("File not found: " + _hdriPath, MessageType.Error);
                return;
            }

            _isImporting = true;
            SetStatus("Importing HDRI...", MessageType.Info);
            Repaint();

            try
            {
                ImportAndApplyHDRI(
                    _hdriPath, _cubemapResolution,
                    _applyAsSkybox, _updateEnvironmentLighting, _updateReflections,
                    _exposureOverride, _rotationOffset, _tintColor
                );
                SetStatus("HDRI imported successfully!", MessageType.Info);
            }
            catch (Exception ex)
            {
                SetStatus("Import failed: " + ex.Message, MessageType.Error);
                Debug.LogException(ex);
            }
            finally
            {
                _isImporting = false;
                Repaint();
            }
        }

        /// <summary>
        /// Static method to import an HDRI and apply it to the scene.
        /// Can be called from other scripts or the Quick Apply menu.
        /// </summary>
        public static void ImportAndApplyHDRI(
            string filePath, int cubemapResolution,
            bool applyAsSkybox, bool updateLighting, bool updateReflections,
            float exposure, float rotation, Color tint)
        {
            // Step 1: Copy HDR file to Assets if not already there
            string assetPath = CopyToAssets(filePath);

            // Step 2: Import the texture with HDR settings
            ConfigureTextureImporter(assetPath, cubemapResolution);

            // Step 3: Load the imported texture
            AssetDatabase.Refresh();
            var hdriTexture = AssetDatabase.LoadAssetAtPath<Texture2D>(assetPath);
            if (hdriTexture == null)
            {
                throw new Exception("Failed to load HDRI texture from: " + assetPath);
            }

            // Step 4: Create or update Skybox material
            if (applyAsSkybox)
            {
                string matPath = Path.ChangeExtension(assetPath, ".mat");
                Material skyMat = AssetDatabase.LoadAssetAtPath<Material>(matPath);

                if (skyMat == null)
                {
                    skyMat = new Material(Shader.Find("Skybox/Panoramic"));
                    AssetDatabase.CreateAsset(skyMat, matPath);
                }

                skyMat.shader = Shader.Find("Skybox/Panoramic");
                skyMat.SetTexture("_MainTex", hdriTexture);
                skyMat.SetFloat("_Exposure", exposure);
                skyMat.SetFloat("_Rotation", rotation);
                skyMat.SetColor("_Tint", tint);

                EditorUtility.SetDirty(skyMat);
                RenderSettings.skybox = skyMat;
            }

            // Step 5: Update environment lighting settings
            if (updateLighting)
            {
                RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Skybox;
                RenderSettings.ambientIntensity = 1.0f;
                DynamicGI.UpdateEnvironment();
            }

            // Step 6: Update reflection probes
            if (updateReflections)
            {
                RenderSettings.defaultReflectionMode = UnityEngine.Rendering.DefaultReflectionMode.Skybox;
                RenderSettings.defaultReflectionResolution = cubemapResolution;
                DynamicGI.UpdateEnvironment();
            }

            AssetDatabase.SaveAssets();
            Debug.Log($"[HDRI Maker] Successfully imported HDRI: {Path.GetFileName(filePath)}");
        }

        // ============================
        //  Helper Methods
        // ============================
        private static string CopyToAssets(string sourcePath)
        {
            string fileName = Path.GetFileName(sourcePath);
            string destDir = Path.Combine(Application.dataPath, "HDRIMaker", "Environments");

            if (!Directory.Exists(destDir))
                Directory.CreateDirectory(destDir);

            string destPath = Path.Combine(destDir, fileName);

            // Only copy if source is outside the Assets folder
            if (!sourcePath.StartsWith(Application.dataPath))
            {
                File.Copy(sourcePath, destPath, true);
            }
            else
            {
                destPath = sourcePath;
            }

            // Convert to relative asset path
            string assetPath = "Assets" + destPath.Substring(Application.dataPath.Length).Replace('\\', '/');
            return assetPath;
        }

        private static void ConfigureTextureImporter(string assetPath, int cubemapResolution)
        {
            AssetDatabase.ImportAsset(assetPath, ImportAssetOptions.ForceUpdate);
            var importer = AssetImporter.GetAtPath(assetPath) as TextureImporter;

            if (importer != null)
            {
                importer.textureType = TextureImporterType.Default;
                importer.sRGBTexture = false;  // HDR is linear
                importer.alphaSource = TextureImporterAlphaSource.None;
                importer.maxTextureSize = cubemapResolution * 2;
                importer.textureCompression = TextureImporterCompression.Uncompressed;
                importer.wrapMode = TextureWrapMode.Clamp;
                importer.filterMode = FilterMode.Trilinear;
                importer.anisoLevel = 8;
                importer.SaveAndReimport();
            }
        }

        private void LoadPreview()
        {
            if (!File.Exists(_hdriPath))
            {
                _previewTexture = null;
                return;
            }

            try
            {
                byte[] fileData = File.ReadAllBytes(_hdriPath);
                _previewTexture = new Texture2D(2, 2);
                if (!_previewTexture.LoadImage(fileData))
                {
                    _previewTexture = null;
                    SetStatus("Could not load preview (HDR format may not support preview)", MessageType.Warning);
                }
            }
            catch
            {
                _previewTexture = null;
            }

            Repaint();
        }

        private void HandleDragAndDrop(Rect dropArea)
        {
            Event evt = Event.current;
            if (evt.type == EventType.DragUpdated || evt.type == EventType.DragPerform)
            {
                if (!dropArea.Contains(evt.mousePosition))
                    return;

                DragAndDrop.visualMode = DragAndDropVisualMode.Copy;

                if (evt.type == EventType.DragPerform)
                {
                    DragAndDrop.AcceptDrag();
                    foreach (string path in DragAndDrop.paths)
                    {
                        string ext = Path.GetExtension(path).ToLower();
                        if (ext == ".hdr" || ext == ".exr" || ext == ".png")
                        {
                            _hdriPath = path;
                            LoadPreview();
                            break;
                        }
                    }
                }
                evt.Use();
            }
        }

        private void SetStatus(string message, MessageType type)
        {
            _statusMessage = message;
            _statusType = type;
        }

        private void DrawSeparator()
        {
            EditorGUILayout.Space(2);
            var rect = EditorGUILayout.GetControlRect(false, 1);
            rect.height = 1;
            EditorGUI.DrawRect(rect, new Color(0.5f, 0.5f, 0.5f, 0.3f));
            EditorGUILayout.Space(2);
        }

        private void OnDestroy()
        {
            if (_previewTexture != null)
                DestroyImmediate(_previewTexture);
        }
    }
}

#endif // UNITY_EDITOR
