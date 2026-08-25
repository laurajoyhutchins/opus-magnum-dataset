using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using Quintessential;

namespace OpusCorpusOfficialPuzzleExtractor;

public sealed class OfficialPuzzleExtractor : QuintessentialMod
{
    private const string DumpEnvironmentVariable = "OPUS_CORPUS_PUZZLE_DUMP";
    private const int MaximumTraversalDepth = 8;

    public override void Load()
    {
    }

    public override void PostLoad()
    {
    }

    public override void Unload()
    {
    }

    public override void LoadPuzzleContent()
    {
        string configuredDestination = Environment.GetEnvironmentVariable(DumpEnvironmentVariable);
        if (string.IsNullOrWhiteSpace(configuredDestination))
        {
            return;
        }

        string destination = Path.GetFullPath(configuredDestination);
        if (File.Exists(destination) || Directory.Exists(destination))
        {
            throw new InvalidOperationException(
                $"{DumpEnvironmentVariable} must name a fresh path: {destination}"
            );
        }

        string parent = Path.GetDirectoryName(destination);
        if (string.IsNullOrEmpty(parent))
        {
            throw new InvalidOperationException($"invalid dump destination: {destination}");
        }
        Directory.CreateDirectory(parent);

        string candidate = Path.Combine(
            parent,
            $".{Path.GetFileName(destination)}.candidate-{Guid.NewGuid():N}"
        );
        Directory.CreateDirectory(candidate);

        try
        {
            IReadOnlyCollection<Puzzle> puzzles = DiscoverVanillaPuzzles();
            if (puzzles.Count == 0)
            {
                throw new InvalidOperationException("no vanilla Puzzle objects were discovered");
            }

            foreach (Puzzle puzzle in puzzles)
            {
                WritePuzzle(candidate, puzzle);
            }

            if (Directory.EnumerateFiles(candidate, "*.puzzle").Any() == false)
            {
                throw new InvalidOperationException("the official puzzle dump is empty");
            }

            Directory.Move(candidate, destination);
            candidate = null;
        }
        finally
        {
            if (candidate != null && Directory.Exists(candidate))
            {
                Directory.Delete(candidate, recursive: true);
            }
        }
    }

    private static IReadOnlyCollection<Puzzle> DiscoverVanillaPuzzles()
    {
        Assembly gameAssembly = typeof(Puzzle).Assembly;
        Type campaignsType = gameAssembly.GetType("Campaigns", throwOnError: false);
        Type journalVolumesType = gameAssembly.GetType("JournalVolumes", throwOnError: false);
        if (campaignsType == null || journalVolumesType == null)
        {
            throw new InvalidOperationException(
                "could not resolve Campaigns and JournalVolumes from the patched game assembly"
            );
        }

        var queue = new Queue<(object Value, int Depth)>();
        EnqueueStaticFieldValues(queue, campaignsType);
        EnqueueStaticFieldValues(queue, journalVolumesType);

        var visited = new HashSet<object>(ReferenceComparer<object>.Instance);
        var puzzles = new HashSet<Puzzle>(ReferenceComparer<Puzzle>.Instance);

        while (queue.Count > 0)
        {
            (object value, int depth) = queue.Dequeue();
            if (value == null || depth > MaximumTraversalDepth || value is string)
            {
                continue;
            }
            if (value is Puzzle puzzle)
            {
                puzzles.Add(puzzle);
                continue;
            }
            if (!visited.Add(value))
            {
                continue;
            }

            if (value is IEnumerable enumerable)
            {
                foreach (object item in enumerable)
                {
                    if (item != null)
                    {
                        queue.Enqueue((item, depth + 1));
                    }
                }
                continue;
            }

            Type type = value.GetType();
            if (type.Assembly != gameAssembly || !IsPuzzleContainerType(type))
            {
                continue;
            }

            foreach (FieldInfo field in type.GetFields(
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic
            ))
            {
                object child;
                try
                {
                    child = field.GetValue(value);
                }
                catch
                {
                    continue;
                }
                if (child != null)
                {
                    queue.Enqueue((child, depth + 1));
                }
            }
        }

        return puzzles;
    }

    private static void EnqueueStaticFieldValues(Queue<(object Value, int Depth)> queue, Type type)
    {
        foreach (FieldInfo field in type.GetFields(
            BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic
        ))
        {
            object value;
            try
            {
                value = field.GetValue(null);
            }
            catch
            {
                continue;
            }
            if (value != null)
            {
                queue.Enqueue((value, 0));
            }
        }
    }

    private static bool IsPuzzleContainerType(Type type)
    {
        string name = type.Name;
        return name.Contains("Campaign", StringComparison.Ordinal)
            || name.Contains("Journal", StringComparison.Ordinal);
    }

    private static void WritePuzzle(string candidate, Puzzle puzzle)
    {
        string temporaryPath = Path.Combine(candidate, ".current.puzzle");
        if (File.Exists(temporaryPath))
        {
            File.Delete(temporaryPath);
        }

        puzzle.method_1248(temporaryPath);
        byte[] payload = File.ReadAllBytes(temporaryPath);
        File.Delete(temporaryPath);

        string digest;
        using (SHA256 sha256 = SHA256.Create())
        {
            digest = string.Concat(sha256.ComputeHash(payload).Select(value => value.ToString("x2")));
        }

        string destination = Path.Combine(candidate, digest + ".puzzle");
        if (File.Exists(destination))
        {
            if (!File.ReadAllBytes(destination).SequenceEqual(payload))
            {
                throw new InvalidOperationException($"SHA-256 collision at {destination}");
            }
            return;
        }
        File.WriteAllBytes(destination, payload);
    }

    private sealed class ReferenceComparer<T> : IEqualityComparer<T> where T : class
    {
        public static readonly ReferenceComparer<T> Instance = new ReferenceComparer<T>();

        public bool Equals(T left, T right)
        {
            return ReferenceEquals(left, right);
        }

        public int GetHashCode(T value)
        {
            return RuntimeHelpers.GetHashCode(value);
        }
    }
}
